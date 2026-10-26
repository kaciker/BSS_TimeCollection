"""Aggregate-only operational snapshot queries for service monitoring."""
from datetime import timedelta, timezone

from sqlalchemy import func, select, text

from app.core.config import settings
from app.db.session import engine
from app.domain.enums import DeliveryStatus
from app.models.perimeter import FactoryPerimeterEvent
from app.models.time_event import TimeEvent
from app.models.transmission_attempt import TransmissionAttempt
from app.models.worker_runtime_metrics import WorkerRuntimeMetrics

WINDOW_SECONDS = 86_400
ATTEMPT_RESULTS = ("SENT", "RETRY", "REJECTED", "UNKNOWN")
EVENT_STATUSES = tuple(status.value for status in DeliveryStatus)


def _utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _aware(value):
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def collect_operational_metrics():
    """Use a bounded, read-only snapshot and select aggregate values only."""
    connection = engine.connect()
    if connection.dialect.name == "postgresql":
        connection = connection.execution_options(isolation_level="REPEATABLE READ")
    with connection as conn:
        with conn.begin():
            if conn.dialect.name == "postgresql":
                conn.execute(text("SET TRANSACTION READ ONLY"))
                timeout_ms = max(1, min(settings.operational_statement_timeout_ms, 750))
                conn.execute(text(f"SET LOCAL statement_timeout = '{timeout_ms}ms'"))

            db_now = func.clock_timestamp() if conn.dialect.name == "postgresql" else func.current_timestamp()
            collected_at = conn.scalar(select(db_now))
            if collected_at.tzinfo is None:
                collected_at = collected_at.replace(tzinfo=timezone.utc)
            cutoff = collected_at - timedelta(seconds=WINDOW_SECONDS)

            event_rows = conn.execute(
                select(TimeEvent.delivery_status, func.count()).group_by(TimeEvent.delivery_status)
            ).all()
            counts = {status: 0 for status in EVENT_STATUSES}
            for status, count in event_rows:
                if status not in counts:
                    raise RuntimeError("unrecognized event delivery status")
                counts[status] = int(count)
            pending_oldest = conn.scalar(
                select(func.min(TimeEvent.created_at)).where(
                    TimeEvent.delivery_status == DeliveryStatus.PENDING.value
                )
            )
            attempt_rows = conn.execute(
                select(TransmissionAttempt.result, func.count())
                .where(TransmissionAttempt.started_at >= cutoff, TransmissionAttempt.started_at <= collected_at)
                .group_by(TransmissionAttempt.result)
            ).all()
            attempt_counts = {status: 0 for status in ATTEMPT_RESULTS}
            for status, count in attempt_rows:
                if status not in attempt_counts:
                    raise RuntimeError("unrecognized transmission result")
                attempt_counts[status] = int(count)
            last_attempt = conn.scalar(
                select(func.max(TransmissionAttempt.started_at)).where(
                    TransmissionAttempt.started_at >= cutoff,
                    TransmissionAttempt.started_at <= collected_at,
                )
            )
            local_only_count = conn.scalar(
                select(func.count()).select_from(FactoryPerimeterEvent).where(
                    FactoryPerimeterEvent.event_datetime >= cutoff,
                    FactoryPerimeterEvent.event_datetime <= collected_at,
                )
            )
            runtime = conn.execute(
                select(
                    WorkerRuntimeMetrics.heartbeat_at,
                    WorkerRuntimeMetrics.last_successful_cycle_at,
                    WorkerRuntimeMetrics.last_successful_delivery_at,
                ).where(WorkerRuntimeMetrics.id == 1)
            ).one_or_none()
            stale_cutoff = collected_at - timedelta(seconds=settings.worker_stale_sending_seconds)
            stale_sending_count = conn.scalar(
                select(func.count()).select_from(TimeEvent).where(
                    TimeEvent.delivery_status == DeliveryStatus.SENDING.value,
                    TimeEvent.last_attempt_at < stale_cutoff,
                )
            )

        heartbeat, cycle, delivery = runtime if runtime else (None, None, None)
        pending_oldest, heartbeat, cycle, delivery = map(_aware, (pending_oldest, heartbeat, cycle, delivery))
        pending_age = max(0, int((collected_at - pending_oldest).total_seconds())) if pending_oldest else None
        heartbeat_age = max(0, int((collected_at - heartbeat).total_seconds())) if heartbeat else None
        fresh = heartbeat_age is not None and heartbeat_age <= settings.worker_heartbeat_stale_seconds
        process_status = "UNKNOWN" if heartbeat is None else ("RUNNING" if fresh else "STALE")
        if not settings.oracle_enabled:
            processing_status = "DISABLED"
        elif not fresh:
            processing_status = "UNKNOWN"
        elif cycle is None or (collected_at - cycle).total_seconds() > settings.worker_heartbeat_stale_seconds:
            processing_status = "STALLED"
        else:
            processing_status = "PROCESSING" if counts[DeliveryStatus.SENDING.value] else "IDLE"

        return {
            "contract_version": 1,
            "collected_at": _utc(collected_at),
            "oracle": {"status": "ENABLED" if settings.oracle_enabled else "DISABLED"},
            "worker": {
                "process_status": process_status,
                "processing_status": processing_status,
                "heartbeat_at": _utc(heartbeat),
                "heartbeat_age_seconds": heartbeat_age,
                "last_successful_cycle_at": _utc(cycle),
                "last_successful_delivery_at": _utc(delivery),
            },
            "events": {
                "by_delivery_status": counts,
                "pending_count": counts[DeliveryStatus.PENDING.value],
                "oldest_pending_created_at": _utc(pending_oldest),
                "oldest_pending_age_seconds": pending_age,
                "retrying_count": counts[DeliveryStatus.RETRY.value],
                "failed_count": counts[DeliveryStatus.REJECTED.value],
                "unknown_count": counts[DeliveryStatus.UNKNOWN.value],
                "in_flight_count": counts[DeliveryStatus.SENDING.value],
                "stale_sending_count": int(stale_sending_count or 0),
            },
            "transmission_attempts_24h": {
                "window_seconds": WINDOW_SECONDS,
                "total": sum(attempt_counts.values()),
                "by_result": attempt_counts,
                "last_attempt_at": _utc(last_attempt),
            },
            "perimeter_24h": {"window_seconds": WINDOW_SECONDS, "local_only_count": int(local_only_count or 0)},
        }
