from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.core.config import settings
from app.core.oracle_credentials import get_oracle_credentials
from app.models.time_event import TimeEvent


class OracleMappingError(ValueError):
    """An event is retained locally but cannot be sent under the Oracle contract."""


@dataclass
class DeliveryResult:
    result: str
    retryable: bool
    ambiguous: bool
    status_code: int | None
    duration_ms: int
    request_payload: dict[str, Any]
    response_payload: dict[str, Any] | None
    error_message: str | None
    oracle_request_id: str | None = None
    oracle_event_id: str | None = None


class OracleClient:
    @property
    def endpoint(self) -> str:
        return f"{settings.oracle_base_url.rstrip('/')}{settings.oracle_api_path}"

    def build_payload(self, event: TimeEvent) -> dict[str, Any]:
        # Oracle metadata defines requestNumber as an 80-character field.
        if not event.request_number or len(event.request_number) > 80:
            event.oracle_mapping_error = "Oracle requestNumber exceeds the described 80-character limit"
            raise OracleMappingError(event.oracle_mapping_error)
        # oracle_reporter_id used to fall back to the badge. Only the frozen
        # resolved Person ID is valid for this POC.
        reporter_id = event.person_id
        if not reporter_id or not reporter_id.strip():
            event.oracle_mapping_error = "Resolved Person ID is missing; event requires identity reconciliation"
            raise OracleMappingError(event.oracle_mapping_error)
        if not all((event.workshop_code, event.subworkshop_code, event.project_line_code)):
            event.oracle_mapping_error = "Workshop / Subworkshop / Project-Line snapshot is incomplete"
            raise OracleMappingError(event.oracle_mapping_error)
        expected_supplier = event.oracle_supplier_event
        if not expected_supplier:
            event.oracle_mapping_error = "Oracle supplier device event is missing; action mapping requires reconciliation"
            raise OracleMappingError(event.oracle_mapping_error)
        expected_effect = {"HUT_TCD_SUPP1_IN_2": "ENTER", "HUT_TCD_SUPP1_OUT_2": "EXIT"}.get(expected_supplier)
        if expected_effect and event.state_effect != expected_effect:
            event.oracle_mapping_error = f"{expected_supplier} is incompatible with {event.state_effect} direction"
            raise OracleMappingError(event.oracle_mapping_error)
        local_time = event.event_datetime.astimezone(ZoneInfo(event.event_timezone))
        oracle_event: dict[str, Any] = {
            "deviceId": event.device_id,
            "eventDateTime": local_time.isoformat(timespec="milliseconds"),
            "supplierDeviceEvent": expected_supplier,
            "reporterId": reporter_id,
            "reporterIdType": settings.oracle_person_reporter_id_type,
        }
        attributes = {key: value for key, value in (event.oracle_attributes or {}).items()
                      if key not in {"work_cell", "WORK_AREA", "MACHINE", "CELL", "PayrollTimeType"}}
        if event.oracle_payroll_time_type:
            attributes["PayrollTimeType"] = event.oracle_payroll_time_type
        attributes.update({"WORK_AREA": event.workshop_code,
                           "MACHINE": event.subworkshop_code,
                           "CELL": event.project_line_code})
        invalid_attributes = [
            (name, len(str(value)))
            for name, value in attributes.items()
            if len(str(name)) > 240 or len(str(value)) > 150
        ]
        if invalid_attributes:
            name, value_length = invalid_attributes[0]
            event.oracle_mapping_error = (
                f"Oracle time-event attribute exceeds the described schema limit "
                f"(name length {len(str(name))}/240, value length {value_length}/150)"
            )
            raise OracleMappingError(event.oracle_mapping_error)
        oracle_event["timeEventAttributes"] = [
            {"name": key, "value": str(value)} for key, value in attributes.items()
        ]
        request_number = event.request_number
        if len(request_number) > 80:
            event.oracle_mapping_error = f"Oracle requestNumber exceeds the described 80-character limit ({len(request_number)})"
            raise OracleMappingError(event.oracle_mapping_error)
        if len(settings.oracle_source_id) > 40:
            event.oracle_mapping_error = "Configured Oracle sourceId exceeds the described 40-character limit"
            raise OracleMappingError(event.oracle_mapping_error)
        return {
            "requestNumber": request_number,
            "sourceId": settings.oracle_source_id,
            # Timestamp equality is pending HR-Path confirmation. Keep capture
            # time in eventDateTime and actual transmission time in this field.
            "requestTimestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "timeEvents": [oracle_event],
        }

    def _auth(self):
        credentials = get_oracle_credentials()
        if credentials["auth_mode"] == "basic":
            return httpx.BasicAuth(credentials["username"], credentials["password"])
        return None

    def _headers(self) -> dict[str, str]:
        credentials = get_oracle_credentials()
        headers = {"Accept": "application/json", "Content-Type": "application/json",
                   "REST-Framework-Version": settings.oracle_rest_framework_version}
        if credentials["auth_mode"] == "bearer" and credentials["bearer_token"]:
            headers["Authorization"] = f"Bearer {credentials['bearer_token']}"
        return headers

    def send(self, event: TimeEvent) -> DeliveryResult:
        payload = self.build_payload(event)
        started = monotonic()
        try:
            with httpx.Client(timeout=settings.oracle_timeout_seconds) as client:
                response = client.post(self.endpoint, json=payload, headers=self._headers(), auth=self._auth())
            duration_ms = int((monotonic() - started) * 1000)
            try:
                body = response.json()
            except ValueError:
                body = {"raw": response.text[:4000]}

            if 200 <= response.status_code < 300:
                request_id = body.get("timeEventRequestId") if isinstance(body, dict) else None
                event_id = None
                if isinstance(body, dict):
                    events = body.get("timeEvents") or body.get("items") or []
                    if events and isinstance(events, list) and isinstance(events[0], dict):
                        event_id = events[0].get("timeEventId")
                return DeliveryResult("SENT", False, False, response.status_code, duration_ms, payload, body, None, request_id, event_id)

            # Without a tenant-confirmed idempotency guarantee, server timeouts
            # and 5xx responses may follow a committed event. Do not replay them.
            ambiguous = response.status_code == 408 or response.status_code >= 500
            retryable = response.status_code in {425, 429}
            return DeliveryResult(
                "UNKNOWN" if ambiguous else "RETRY" if retryable else "REJECTED",
                retryable,
                ambiguous,
                response.status_code,
                duration_ms,
                payload,
                body,
                f"Oracle returned HTTP {response.status_code}",
            )
        except (httpx.ReadTimeout, httpx.WriteTimeout) as exc:
            return DeliveryResult("UNKNOWN", False, True, None, int((monotonic() - started) * 1000), payload, None, str(exc))
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            return DeliveryResult("RETRY", True, False, None, int((monotonic() - started) * 1000), payload, None, str(exc))
        except httpx.HTTPError as exc:
            # Other protocol failures can occur after Oracle received the body.
            return DeliveryResult("UNKNOWN", False, True, None, int((monotonic() - started) * 1000), payload, None, str(exc))
