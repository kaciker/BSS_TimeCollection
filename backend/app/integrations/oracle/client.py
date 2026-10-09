from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.core.config import settings
from app.models.time_event import TimeEvent


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
        local_time = event.event_datetime.astimezone(ZoneInfo(event.event_timezone))
        oracle_event: dict[str, Any] = {
            "deviceId": event.device_id,
            "eventDateTime": local_time.isoformat(timespec="milliseconds"),
            "supplierDeviceEvent": event.supplier_device_event,
            "reporterId": event.reporter_id,
            "reporterIdType": event.reporter_id_type,
        }
        if event.oracle_attributes:
            oracle_event["timeEventAttributes"] = [
                {"name": key, "value": str(value)} for key, value in event.oracle_attributes.items()
            ]
        return {
            "requestNumber": event.request_number,
            "sourceId": settings.oracle_source_id,
            "requestTimestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "timeEvents": [oracle_event],
        }

    def _auth(self):
        if settings.oracle_auth_mode.lower() == "basic":
            return httpx.BasicAuth(settings.oracle_username, settings.oracle_password)
        return None

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if settings.oracle_auth_mode.lower() == "bearer" and settings.oracle_bearer_token:
            headers["Authorization"] = f"Bearer {settings.oracle_bearer_token}"
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

            retryable = response.status_code in {408, 425, 429} or response.status_code >= 500
            return DeliveryResult(
                "RETRY" if retryable else "REJECTED",
                retryable,
                False,
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
            return DeliveryResult("RETRY", True, False, None, int((monotonic() - started) * 1000), payload, None, str(exc))
