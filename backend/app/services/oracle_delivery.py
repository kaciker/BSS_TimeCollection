import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from app.core.config import settings
from app.db.session import SessionLocal
from app.domain.enums import DeliveryStatus
from app.integrations.oracle.client import OracleClient, OracleMappingError
from app.models.time_event import TimeEvent
from app.models.transmission_attempt import TransmissionAttempt

logger = logging.getLogger("delivery-worker")


def deliver_event(
    event_id: str,
    client: OracleClient,
    *,
    session_factory=SessionLocal,
    metrics_callback=None,
) -> None:
    """Send one already-claimed event and persist the normal delivery audit."""
    with session_factory() as db:
        event = db.get(TimeEvent, event_id)
        if event is None:
            return
        started_at = datetime.now(timezone.utc)
        try:
            result = client.send(event)
        except OracleMappingError as exc:
            event.delivery_status = DeliveryStatus.REJECTED.value
            event.next_attempt_at = None
            db.add(TransmissionAttempt(
                event_id=event.id,
                attempt_number=event.attempt_count,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                endpoint=client.endpoint,
                http_status=None,
                result=DeliveryStatus.REJECTED.value,
                duration_ms=0,
                request_payload={},
                response_payload=None,
                error_message=str(exc),
                retryable=False,
                ambiguous=False,
                oracle_request_id=None,
                oracle_event_id=None,
            ))
            db.commit()
            logger.error("Event mapping requires reconciliation event=%s reason=%s", event.id, exc)
            return
        finished_at = datetime.now(timezone.utc)

        db.add(TransmissionAttempt(
            event_id=event.id,
            attempt_number=event.attempt_count,
            started_at=started_at,
            finished_at=finished_at,
            endpoint=client.endpoint,
            http_status=result.status_code,
            result=result.result,
            duration_ms=result.duration_ms,
            request_payload=result.request_payload,
            response_payload=result.response_payload,
            error_message=result.error_message,
            retryable=result.retryable,
            ambiguous=result.ambiguous,
            oracle_request_id=str(result.oracle_request_id) if result.oracle_request_id is not None else None,
            oracle_event_id=str(result.oracle_event_id) if result.oracle_event_id is not None else None,
        ))

        event.delivery_status = result.result
        if result.result == DeliveryStatus.SENT.value:
            event.sent_at = finished_at
            event.next_attempt_at = None
            event.oracle_request_id = str(result.oracle_request_id) if result.oracle_request_id is not None else None
            event.oracle_event_id = str(result.oracle_event_id) if result.oracle_event_id is not None else None
        elif result.retryable:
            delay_seconds = min(5 * (2 ** max(event.attempt_count - 1, 0)), 600)
            event.next_attempt_at = finished_at + timedelta(seconds=delay_seconds)
        else:
            event.next_attempt_at = None
        db.commit()
        if result.result == DeliveryStatus.SENT.value:
            try:
                if metrics_callback is not None:
                    metrics_callback(successful_delivery=True)
            except Exception:
                logger.warning("Worker successful-delivery metric update failed")
        logger.info("Delivery result event=%s status=%s http=%s", event.id, result.result, result.status_code)


def validate_sendable_event(event: TimeEvent, client: OracleClient) -> dict:
    """Validate an event without persisting changes and return its exact payload."""
    if event.delivery_status == "LOCAL_ONLY" or (
        event.terminal is not None and event.terminal.terminal_role != "CELL"
    ):
        raise ValueError("LOCAL_ONLY/perimeter events cannot be sent to Oracle")
    if event.delivery_status in {DeliveryStatus.SENT.value, DeliveryStatus.SENDING.value}:
        raise ValueError(f"Event status {event.delivery_status} cannot be sent")
    if event.delivery_status == DeliveryStatus.UNKNOWN.value:
        raise ValueError("UNKNOWN delivery requires read-only reconciliation before any resend")
    if event.delivery_status not in {DeliveryStatus.PENDING.value, DeliveryStatus.RETRY.value, DeliveryStatus.REJECTED.value}:
        raise ValueError(f"Event status {event.delivery_status} is not eligible for explicit delivery")
    if not event.person_id or not event.person_id.strip():
        raise ValueError("Resolved Person ID is missing")
    if not event.oracle_payroll_time_type or not event.oracle_payroll_time_type.strip():
        raise ValueError("PayrollTimeType is missing")
    for label, value in (
        ("WORK_AREA", event.workshop_code),
        ("MACHINE", event.subworkshop_code),
        ("CELL", event.project_line_code),
    ):
        if not value or not value.strip():
            raise ValueError(f"{label} structure is missing")
    expected_supplier = {
        "ENTER": "HUT_TCD_SUPP1_IN_2",
        "EXIT": "HUT_TCD_SUPP1_OUT_2",
    }.get(event.state_effect)
    if not expected_supplier or event.oracle_supplier_event != expected_supplier:
        raise ValueError("Oracle supplier event/direction mapping is invalid")
    if not event.request_number or len(event.request_number) > 80 or not event.request_number.strip():
        raise ValueError("Oracle requestNumber is missing or invalid")
    return client.build_payload(event)


def send_one_event(
    event_id: str,
    *,
    send: bool,
    confirm_request_number: str | None = None,
    client: OracleClient | None = None,
    session_factory=SessionLocal,
) -> dict:
    """Preview or explicitly send only the supplied event ID."""
    client = client or OracleClient()
    if send and settings.oracle_enabled:
        raise ValueError("Explicit one-event delivery requires ORACLE_ENABLED=false for the normal worker")
    with session_factory() as db:
        statement = select(TimeEvent).where(TimeEvent.id == event_id).with_for_update()
        event = db.scalar(statement)
        if event is None:
            raise ValueError("Event does not exist")
        payload = validate_sendable_event(event, client)
        if not send:
            return {"sent": False, "payload": payload}
        if confirm_request_number != event.request_number:
            raise ValueError("--confirm-request-number must exactly match this event's requestNumber")
        event.delivery_status = DeliveryStatus.SENDING.value
        event.attempt_count += 1
        event.last_attempt_at = datetime.now(timezone.utc)
        db.commit()

    deliver_event(event_id, client, session_factory=session_factory)
    with session_factory() as db:
        event = db.get(TimeEvent, event_id)
        attempt = db.scalar(
            select(TransmissionAttempt)
            .where(TransmissionAttempt.event_id == event_id)
            .order_by(TransmissionAttempt.id.desc())
            .limit(1)
        )
        return {
            "sent": True,
            "delivery_status": event.delivery_status,
            "oracle_request_id": event.oracle_request_id,
            "oracle_event_id": event.oracle_event_id,
            "attempt_id": attempt.id if attempt else None,
        }
