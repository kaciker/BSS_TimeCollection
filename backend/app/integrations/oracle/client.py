from dataclasses import dataclass
from datetime import timezone
from time import monotonic
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.core.config import settings
from app.core.oracle_credentials import get_oracle_credentials
from app.models.time_event import TimeEvent
from app.services.oracle_readiness import oracle_readiness_errors


class OracleMappingError(ValueError):
    """An event is retained locally but cannot be sent under the Oracle contract."""


def _extract_event_id(body: Any) -> Any:
    """Extract an event ID from known Oracle response collection shapes only."""
    if not isinstance(body, dict):
        return None
    candidates: list[Any] = []
    time_events = body.get("timeEvents")
    if isinstance(time_events, dict):
        candidates = time_events.get("items", [])
    elif isinstance(time_events, list):
        candidates = time_events
    if not candidates:
        items = body.get("items")
        if isinstance(items, list):
            candidates = items
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get("timeEventId") is not None:
                return candidate["timeEventId"]
    return None


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
        # A client payload is built exclusively from frozen, catalogue-valid
        # Oracle fields. Legacy/local structures and arbitrary JSON attributes
        # are intentionally not payload sources.
        # Oracle metadata defines requestNumber as an 80-character field.
        if not event.request_number or len(event.request_number) > 80:
            event.oracle_mapping_error = "Oracle requestNumber exceeds the described 80-character limit"
            raise OracleMappingError(event.oracle_mapping_error)
        if len(settings.oracle_source_id) > 40:
            event.oracle_mapping_error = "Configured Oracle sourceId exceeds the described 40-character limit"
            raise OracleMappingError(event.oracle_mapping_error)

        errors = oracle_readiness_errors(event)
        if errors:
            event.oracle_mapping_error = "; ".join(errors)[:255]
            raise OracleMappingError(event.oracle_mapping_error)

        # Only the frozen resolved Person ID is valid for this contract. Keep
        # the terminal's raw identifier locally for audit; never send it here.
        reporter_id = event.person_id
        expected_supplier = event.oracle_supplier_event

        # event_datetime is the captured business timestamp. Interpret legacy
        # naive values in the event's captured timezone, then serialize one UTC
        # instant for both Oracle timestamp fields.
        captured_time = event.event_datetime
        if captured_time.tzinfo is None:
            captured_time = captured_time.replace(tzinfo=ZoneInfo(event.event_timezone))
        oracle_timestamp = captured_time.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

        attributes = [
            {"name": "PayrollTimeType", "value": str(event.oracle_payroll_time_type)},
            {"name": "WORK_AREA", "value": str(event.oracle_work_area_code)},
            {"name": "MACHINE", "value": str(event.oracle_machine_code)},
            {"name": "CELL", "value": str(event.oracle_cell_code)},
        ]
        invalid_attributes = [
            (row["name"], len(row["value"]))
            for row in attributes
            if len(row["name"]) > 240 or len(row["value"]) > 150
        ]
        if invalid_attributes:
            name, value_length = invalid_attributes[0]
            event.oracle_mapping_error = (
                "Oracle time-event attribute exceeds the described schema limit "
                f"(name length {len(name)}/240, value length {value_length}/150)"
            )
            raise OracleMappingError(event.oracle_mapping_error)

        oracle_event = {
            "eventDateTime": oracle_timestamp,
            "supplierDeviceEvent": expected_supplier,
            "reporterId": reporter_id,
            "reporterIdType": "PERSON",
            "timeEventAttributes": attributes,
        }
        return {
            "requestNumber": event.request_number,
            "sourceId": settings.oracle_source_id,
            "requestTimestamp": oracle_timestamp,
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
                event_id = _extract_event_id(body)
                return DeliveryResult("SENT", False, False, response.status_code, duration_ms, payload, body, None,
                                      request_id, event_id)

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
