import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update

from app.core.config import settings
from app.db.session import SessionLocal
from app.domain.enums import DeliveryStatus
from app.integrations.oracle.client import OracleClient
from app.models.time_event import TimeEvent
from app.models.transmission_attempt import TransmissionAttempt

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("delivery-worker")


def recover_stale_events() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.worker_stale_sending_seconds)
    with SessionLocal() as db:
        db.execute(
            update(TimeEvent)
            .where(TimeEvent.delivery_status == DeliveryStatus.SENDING.value)
            .where(TimeEvent.last_attempt_at < cutoff)
            .values(delivery_status=DeliveryStatus.RETRY.value, next_attempt_at=datetime.now(timezone.utc))
        )
        db.commit()


def claim_next_event() -> str | None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        event = db.scalar(
            select(TimeEvent)
            .where(TimeEvent.delivery_status.in_([DeliveryStatus.PENDING.value, DeliveryStatus.RETRY.value]))
            .where(or_(TimeEvent.next_attempt_at.is_(None), TimeEvent.next_attempt_at <= now))
            .order_by(TimeEvent.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if event is None:
            return None
        event.delivery_status = DeliveryStatus.SENDING.value
        event.attempt_count += 1
        event.last_attempt_at = now
        db.commit()
        return event.id


def deliver(event_id: str, client: OracleClient) -> None:
    with SessionLocal() as db:
        event = db.get(TimeEvent, event_id)
        if event is None:
            return
        started_at = datetime.now(timezone.utc)
        result = client.send(event)
        finished_at = datetime.now(timezone.utc)

        db.add(
            TransmissionAttempt(
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
            )
        )

        event.delivery_status = result.result
        if result.result == DeliveryStatus.SENT.value:
            event.sent_at = finished_at
            event.next_attempt_at = None
            event.oracle_request_id = result.oracle_request_id
            event.oracle_event_id = result.oracle_event_id
        elif result.retryable:
            delay_seconds = min(5 * (2 ** max(event.attempt_count - 1, 0)), 600)
            event.next_attempt_at = finished_at + timedelta(seconds=delay_seconds)
        else:
            event.next_attempt_at = None
        db.commit()
        logger.info("Delivery result event=%s status=%s http=%s", event.id, result.result, result.status_code)


def main() -> None:
    logger.info("Delivery worker started; Oracle enabled=%s", settings.oracle_enabled)
    recover_stale_events()
    client = OracleClient()
    while True:
        if not settings.oracle_enabled:
            time.sleep(max(settings.worker_poll_seconds, 1.0))
            continue
        event_id = claim_next_event()
        if event_id is None:
            time.sleep(settings.worker_poll_seconds)
            continue
        try:
            deliver(event_id, client)
        except Exception:
            logger.exception("Unhandled delivery failure for event=%s", event_id)
            with SessionLocal() as db:
                event = db.get(TimeEvent, event_id)
                if event and event.delivery_status == DeliveryStatus.SENDING.value:
                    event.delivery_status = DeliveryStatus.RETRY.value
                    event.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=30)
                    db.commit()


if __name__ == "__main__":
    main()
