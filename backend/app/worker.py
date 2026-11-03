import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update

from app.core.config import settings
from app.db.session import SessionLocal
from app.domain.enums import DeliveryStatus
from app.integrations.oracle.client import OracleClient
from app.models.time_event import TimeEvent
from app.models.worker_runtime_metrics import WorkerRuntimeMetrics
from app.services.oracle_delivery import deliver_event
from app.services.oracle_readiness import is_oracle_ready
from app.services.external_perimeter_sync import (
    reconcile_enabled_external_perimeters,
    sync_enabled_external_perimeters,
)
from app.services.factory_presence import reconcile_enabled_factory_presence
from app.services.person_identity import sync_enabled_person_badges

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("delivery-worker")


def update_runtime_metrics(
    *, process_started=False, heartbeat=False, successful_cycle=False, successful_delivery=False, db=None
) -> None:
    """Update the bounded singleton without storing worker or event identities."""
    now = datetime.now(timezone.utc)

    def apply(session):
        from sqlalchemy.dialects.postgresql import insert as postgres_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        values = {"id": 1, "process_started_at": now}
        if heartbeat:
            values["heartbeat_at"] = now
        if successful_cycle:
            values["last_successful_cycle_at"] = now
        if successful_delivery:
            values["last_successful_delivery_at"] = now
        insert = sqlite_insert if session.bind.dialect.name == "sqlite" else postgres_insert
        statement = insert(WorkerRuntimeMetrics).values(**values)
        update_values = {
            key: getattr(statement.excluded, key)
            for key in values
            if key != "id" and (key != "process_started_at" or process_started)
        }
        session.execute(
            statement.on_conflict_do_update(index_elements=[WorkerRuntimeMetrics.id], set_=update_values)
        )

    if db is not None:
        apply(db)
        return
    with SessionLocal() as session:
        apply(session)
        session.commit()


def _heartbeat_loop(stop: threading.Event) -> None:
    interval = max(1, settings.worker_heartbeat_seconds)
    process_started = True
    while not stop.is_set():
        try:
            update_runtime_metrics(process_started=process_started, heartbeat=True)
            process_started = False
        except Exception:
            logger.warning("Worker heartbeat update failed")
        stop.wait(interval)


def recover_stale_events() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.worker_stale_sending_seconds)
    with SessionLocal() as db:
        result = db.execute(
            update(TimeEvent)
            .where(TimeEvent.delivery_status == DeliveryStatus.SENDING.value)
            .where(TimeEvent.last_attempt_at < cutoff)
            .values(delivery_status=DeliveryStatus.UNKNOWN.value, next_attempt_at=None)
        )
        db.commit()
        if result.rowcount:
            logger.warning(
                "Marked %s stale SENDING event(s) as UNKNOWN; reconciliation is required before replay",
                result.rowcount,
            )


def claim_next_event() -> str | None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        candidate_ids = db.scalars(
            select(TimeEvent)
            .where(TimeEvent.delivery_status.in_([DeliveryStatus.PENDING.value, DeliveryStatus.RETRY.value]))
            .where(or_(TimeEvent.next_attempt_at.is_(None), TimeEvent.next_attempt_at <= now))
            .order_by(TimeEvent.created_at)
            .with_only_columns(TimeEvent.id)
        ).all()
        # Catalogue hierarchy validation lives in one shared service. Rows not
        # ready remain local and pending; the worker never claims them.
        event = None
        for candidate_id in candidate_ids:
            candidate = db.scalar(select(TimeEvent).where(TimeEvent.id == candidate_id).with_for_update(skip_locked=True))
            if (
                candidate is not None
                and candidate.delivery_status in {DeliveryStatus.PENDING.value, DeliveryStatus.RETRY.value}
                and (candidate.next_attempt_at is None or candidate.next_attempt_at <= now)
                and is_oracle_ready(candidate)
            ):
                event = candidate
                break
        if event is None:
            return None
        event.delivery_status = DeliveryStatus.SENDING.value
        event.attempt_count += 1
        event.last_attempt_at = now
        db.commit()
        return event.id


def deliver(event_id: str, client: OracleClient) -> None:
    deliver_event(event_id, client, session_factory=SessionLocal, metrics_callback=update_runtime_metrics)


def main() -> None:
    logger.info(
        "Delivery worker started; Oracle enabled=%s external perimeter sync=%ss person/badge sync=%ss",
        settings.oracle_enabled,
        settings.perimeter_external_sync_seconds,
        settings.person_badge_sync_seconds,
    )
    stop = threading.Event()
    heartbeat = threading.Thread(target=_heartbeat_loop, args=(stop,), name="worker-heartbeat", daemon=True)
    heartbeat.start()
    next_external_sync = 0.0
    next_external_reconciliation = 0.0
    next_factory_presence_reconciliation = 0.0
    next_person_badge_sync = 0.0
    try:
        recover_stale_events()
        client = OracleClient()
        while True:
            now_monotonic = time.monotonic()

            # Refresh the local PERSON ID / reader / card mapping first so any
            # perimeter movement inserted in this cycle can freeze that identity.
            if now_monotonic >= next_person_badge_sync:
                try:
                    changes = sync_enabled_person_badges()
                    if changes:
                        logger.info("Recorded %s person/badge assignment change(s)", changes)
                except Exception:
                    logger.exception("Unhandled person/badge synchronization failure")
                next_person_badge_sync = now_monotonic + max(settings.person_badge_sync_seconds, 30.0)

            if now_monotonic >= next_external_sync:
                try:
                    mirrored = sync_enabled_external_perimeters()
                    if mirrored:
                        logger.info("Mirrored %s external perimeter movement(s)", mirrored)
                except Exception:
                    logger.exception("Unhandled external perimeter replication failure")
                next_external_sync = now_monotonic + max(settings.perimeter_external_sync_seconds, 5.0)

            if now_monotonic >= next_external_reconciliation:
                try:
                    repaired = reconcile_enabled_external_perimeters()
                    if repaired:
                        logger.info("Reconciled %s external perimeter state(s)", repaired)
                except Exception:
                    logger.exception("Unhandled external perimeter reconciliation failure")
                next_external_reconciliation = now_monotonic + 180.0

            if now_monotonic >= next_factory_presence_reconciliation:
                try:
                    changed = reconcile_enabled_factory_presence()
                    if changed:
                        logger.info("Updated %s authoritative factory presence projection row(s)", changed)
                except Exception:
                    logger.exception("Unhandled authoritative factory presence reconciliation failure")
                next_factory_presence_reconciliation = now_monotonic + 180.0

            if not settings.oracle_enabled:
                time.sleep(max(settings.worker_poll_seconds, 1.0))
                continue

            try:
                event_id = claim_next_event()
            except Exception:
                logger.exception("Worker queue cycle failed")
                time.sleep(settings.worker_poll_seconds)
                continue
            try:
                update_runtime_metrics(successful_cycle=True)
            except Exception:
                # Telemetry must never strand an event already claimed by the worker.
                logger.warning("Worker successful-cycle metric update failed")
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
                        event.delivery_status = DeliveryStatus.UNKNOWN.value
                        event.next_attempt_at = None
                        db.commit()
                        logger.warning(
                            "Marked event=%s as UNKNOWN after unhandled delivery failure; reconciliation is required before replay",
                            event.id,
                        )
    finally:
        stop.set()
        heartbeat.join(timeout=max(1, settings.worker_heartbeat_seconds))


if __name__ == "__main__":
    main()
