"""Incremental read-only replication of Arganda SECURITY_DB perimeter movements."""
import logging
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.domain.enums import IdentificationMethod
from app.models.perimeter import FactoryPerimeterEvent, FactoryPerimeterSettings
from app.models.terminal import Terminal
from app.services.external_perimeter import (
    ExternalPerimeterError,
    _connection_string,
    _credentials,
    _safe_odbc_category,
    reader_number_to_attr_value,
)
from app.services.perimeter_service import create_auto_cell_exit_for_factory_exit

logger = logging.getLogger(__name__)
SOURCE = "SQLSERVER_SECURITY_DB"

_HIGH_WATERMARK_SQL = """
SELECT COALESCE(MAX(t.log_id), 0)
FROM dbo.acc_transaction AS t
WHERE t.acc_zone_code IN (1, 2)
"""

_EVENTS_AFTER_SQL = """
SELECT TOP ({limit}) t.log_id, t.event_time, t.acc_zone_code, pae.attr_value4
FROM dbo.acc_transaction AS t
LEFT JOIN dbo.pers_card AS pc ON pc.card_no = t.card_no
LEFT JOIN dbo.pers_person AS p ON p.id = pc.person_id
LEFT JOIN dbo.pers_attribute_ext AS pae ON pae.person_id = p.id
WHERE t.log_id > ? AND t.acc_zone_code IN (1, 2)
ORDER BY t.log_id ASC
"""

_LATEST_BADGE_EVENT_SQL = """
SELECT TOP (1) t.log_id, t.event_time, t.acc_zone_code
FROM dbo.pers_attribute_ext AS pae
JOIN dbo.pers_person AS p ON p.id = pae.person_id
JOIN dbo.pers_card AS pc ON pc.person_id = p.id
JOIN dbo.acc_transaction AS t ON t.card_no = pc.card_no
WHERE pae.attr_value4 = ? AND t.acc_zone_code IN (1, 2)
ORDER BY t.event_time DESC, t.log_id DESC
"""

_CURRENT_INSIDE_SQL = """
WITH latest AS (
    SELECT
        t.log_id,
        t.event_time,
        t.acc_zone_code,
        pae.attr_value4,
        ROW_NUMBER() OVER (
            PARTITION BY pae.attr_value4
            ORDER BY t.log_id DESC, t.event_time DESC
        ) AS rn
    FROM dbo.pers_attribute_ext AS pae
    JOIN dbo.pers_person AS p ON p.id = pae.person_id
    JOIN dbo.pers_card AS pc ON pc.person_id = p.id
    JOIN dbo.acc_transaction AS t ON t.card_no = pc.card_no
    WHERE pae.attr_value4 IS NOT NULL
      AND t.acc_zone_code IN (1, 2)
      AND t.log_id <= ?
)
SELECT log_id, event_time, acc_zone_code, attr_value4
FROM latest
WHERE rn = 1 AND acc_zone_code = 2
ORDER BY log_id ASC
"""

_CURRENT_STATES_SQL = """
WITH latest AS (
    SELECT
        t.log_id, t.event_time, t.acc_zone_code, pae.attr_value4,
        ROW_NUMBER() OVER (
            PARTITION BY pae.attr_value4
            ORDER BY t.log_id DESC, t.event_time DESC
        ) AS rn
    FROM dbo.pers_attribute_ext AS pae
    JOIN dbo.pers_person AS p ON p.id = pae.person_id
    JOIN dbo.pers_card AS pc ON pc.person_id = p.id
    JOIN dbo.acc_transaction AS t ON t.card_no = pc.card_no
    WHERE pae.attr_value4 IS NOT NULL
      AND t.acc_zone_code IN (1, 2)
      AND t.log_id <= ?
)
SELECT log_id, event_time, acc_zone_code, attr_value4
FROM latest
WHERE rn = 1
ORDER BY log_id ASC
"""


def attr_value_to_reader_number(value: str) -> str:
    """Reverse the validated 32-bit byte swap and restore the 10-digit reader format."""
    digits = str(value).strip()
    if not digits or not digits.isascii() or not digits.isdecimal():
        raise ValueError("External badge attribute must contain ASCII decimal digits")
    number = int(digits)
    if number >= 2 ** 32:
        raise ValueError("External badge attribute exceeds the validated 32-bit format")
    reader_number = int.from_bytes(number.to_bytes(4, "big"), "little")
    return f"{reader_number:010d}"


def _connect():
    try:
        import pyodbc
    except ImportError:
        raise ExternalPerimeterError("ODBC_DRIVER_UNAVAILABLE") from None
    config = _credentials()
    try:
        return pyodbc.connect(_connection_string(config), timeout=3, autocommit=True)
    except ExternalPerimeterError:
        raise
    except Exception as exc:
        raise ExternalPerimeterError(_safe_odbc_category(exc, phase="connect")) from None


def external_high_watermark(*, query=None) -> int:
    if query is not None:
        value = query()
        return int(value or 0)
    connection = _connect()
    try:
        row = connection.cursor().execute(_HIGH_WATERMARK_SQL).fetchone()
        return int(row[0] or 0)
    except Exception as exc:
        raise ExternalPerimeterError(_safe_odbc_category(exc, phase="query")) from None
    finally:
        connection.close()


def _normalize_external_row(row, *, reporter_id: str | None = None) -> dict:
    try:
        log_id = int(row[0])
        event_time = row[1]
        zone_code = int(row[2])
        attr_value = row[3] if len(row) > 3 else None
    except (TypeError, ValueError, IndexError):
        return {"log_id": None, "event_time": None, "zone_code": None, "reporter_id": reporter_id}
    if not isinstance(event_time, datetime) or zone_code not in (1, 2):
        return {"log_id": log_id, "event_time": None, "zone_code": zone_code, "reporter_id": reporter_id}
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=ZoneInfo(settings.event_timezone))
    if reporter_id is None and attr_value is not None:
        try:
            reporter_id = attr_value_to_reader_number(str(attr_value))
        except ValueError:
            reporter_id = None
    return {
        "log_id": log_id,
        "event_time": event_time,
        "zone_code": zone_code,
        "reporter_id": reporter_id,
    }


def external_events_after(last_log_id: int, *, limit: int | None = None, query=None) -> list[dict]:
    batch_size = max(1, min(int(limit or settings.perimeter_external_sync_batch_size), 1000))
    if query is not None:
        rows = query(last_log_id, batch_size)
        return [_normalize_external_row(row) for row in rows]
    connection = _connect()
    try:
        sql = _EVENTS_AFTER_SQL.format(limit=batch_size)
        rows = connection.cursor().execute(sql, int(last_log_id)).fetchall()
        return [_normalize_external_row(row) for row in rows]
    except Exception as exc:
        raise ExternalPerimeterError(_safe_odbc_category(exc, phase="query")) from None
    finally:
        connection.close()


def latest_external_event_for_badge(badge: str, *, query=None) -> dict | None:
    converted = reader_number_to_attr_value(badge)
    if query is not None:
        row = query(converted)
    else:
        connection = _connect()
        try:
            row = connection.cursor().execute(_LATEST_BADGE_EVENT_SQL, converted).fetchone()
        except Exception as exc:
            raise ExternalPerimeterError(_safe_odbc_category(exc, phase="query")) from None
        finally:
            connection.close()
    if row is None:
        return None
    return _normalize_external_row(row, reporter_id=badge)


def external_inside_snapshot(max_log_id: int | None = None, *, query=None) -> list[dict]:
    """Return one current INSIDE snapshot per external badge, without importing history."""
    if query is not None:
        rows = query(max_log_id)
    else:
        connection = _connect()
        try:
            rows = connection.cursor().execute(_CURRENT_INSIDE_SQL, int(max_log_id or 0)).fetchall()
        except Exception as exc:
            raise ExternalPerimeterError(_safe_odbc_category(exc, phase="query")) from None
        finally:
            connection.close()
    items = [_normalize_external_row(row) for row in rows]
    return [item for item in items if item.get("zone_code") == 2 and item.get("reporter_id")]


def _virtual_terminal_code(factory_code: str) -> str:
    return f"EXT-{factory_code}"[:64]


def _virtual_device_id(factory_code: str) -> str:
    return f"EXTERNAL-PERIMETER-{factory_code}"[:128]


def ensure_virtual_terminal(db: Session, factory_code: str) -> Terminal:
    code = _virtual_terminal_code(factory_code)
    terminal = db.scalar(select(Terminal).where(Terminal.code == code))
    if terminal is not None:
        if terminal.factory_code != factory_code or terminal.terminal_role != "PERIMETER_BOTH":
            raise RuntimeError(f"Reserved external perimeter terminal code {code} is already in use")
        return terminal
    terminal = Terminal(
        factory_code=factory_code,
        terminal_role="PERIMETER_BOTH",
        code=code,
        name=f"External perimeter mirror - {factory_code}",
        external_device_id=_virtual_device_id(factory_code),
        identification_mode="RFID",
        reporter_id_type="BADGE",
        oracle_attributes={"system_managed": True, "external_source": SOURCE},
        active=False,
    )
    db.add(terminal)
    db.flush()
    return terminal


def _external_event_uuid(factory_code: str, log_id: int) -> str:
    return str(uuid5(NAMESPACE_URL, f"bss-timecollection:{factory_code}:{SOURCE}:{log_id}"))


def _snapshot_event_uuid(factory_code: str, item: dict) -> str:
    """Give current-state snapshots a stable key even when SECURITY_DB omits log_id."""
    log_id = item.get("log_id")
    badge = item.get("reporter_id")
    if log_id is not None and int(log_id) > 0:
        return _external_event_uuid(factory_code, int(log_id))
    return str(uuid5(NAMESPACE_URL, f"bss-timecollection:{factory_code}:{SOURCE}:snapshot:{badge}"))


def _external_correlation_uuid(factory_code: str, log_id: int) -> str:
    return str(uuid5(NAMESPACE_URL, f"bss-timecollection:{factory_code}:{SOURCE}:correlation:{log_id}"))


def mirror_external_event(
    db: Session,
    config: FactoryPerimeterSettings,
    terminal: Terminal,
    item: dict,
) -> bool:
    log_id = item.get("log_id")
    event_time = item.get("event_time")
    zone_code = item.get("zone_code")
    badge = item.get("reporter_id")
    if log_id is None or event_time is None or zone_code not in (1, 2) or not badge:
        return False

    event_id = _snapshot_event_uuid(config.factory_code, item)
    if db.get(FactoryPerimeterEvent, event_id) is not None:
        return False

    direction = "EXIT" if zone_code == 1 else "ENTER"
    correlation_id = _external_correlation_uuid(config.factory_code, log_id)
    auto_event = None
    if direction == "EXIT":
        auto_event = create_auto_cell_exit_for_factory_exit(
            db,
            config,
            config.factory_code,
            badge,
            IdentificationMethod.RFID,
            event_time,
            correlation_id,
            strict=False,
        )
        if auto_event is not None:
            db.flush()

    db.add(
        FactoryPerimeterEvent(
            id=event_id,
            factory_code=config.factory_code,
            reporter_id=badge,
            terminal_id=terminal.id,
            direction=direction,
            event_datetime=event_time,
            correlation_id=correlation_id,
            auto_cell_exit_event_id=auto_event.id if auto_event else None,
        )
    )
    return True


def _bootstrap_external_factory(db: Session, config: FactoryPerimeterSettings, terminal: Terminal) -> int:
    high_watermark = external_high_watermark()
    snapshots = external_inside_snapshot(max_log_id=high_watermark)
    mirrored = 0
    for item in snapshots:
        if mirror_external_event(db, config, terminal, item):
            mirrored += 1
    now = datetime.now(timezone.utc)
    config.external_last_log_id = high_watermark
    config.external_sync_initialized_at = now
    config.external_last_sync_at = now
    config.external_sync_error = None
    db.commit()
    logger.info(
        "External perimeter replication initialized factory=%s cursor=%s inside_snapshots=%s",
        config.factory_code,
        high_watermark,
        mirrored,
    )
    return mirrored


def sync_external_factory(db: Session, config: FactoryPerimeterSettings) -> int:
    if not config.enabled or config.badge_source != "EXTERNAL":
        return 0
    terminal = ensure_virtual_terminal(db, config.factory_code)
    if config.external_sync_initialized_at is None or config.external_last_log_id is None:
        return _bootstrap_external_factory(db, config, terminal)

    mirrored = 0
    unresolved = {"ENTER": 0, "EXIT": 0}
    cursor = int(config.external_last_log_id)
    batch_size = max(1, min(int(settings.perimeter_external_sync_batch_size), 1000))
    for _ in range(10):
        rows = external_events_after(cursor, limit=batch_size)
        if not rows:
            break
        for item in rows:
            log_id = item.get("log_id")
            if log_id is None:
                continue
            if not item.get("reporter_id"):
                direction = "ENTER" if item.get("zone_code") == 2 else "EXIT"
                logger.warning(
                    "Unresolved external perimeter movement factory=%s log_id=%s direction=%s",
                    config.factory_code, log_id, direction,
                )
                unresolved[direction] += 1
            if mirror_external_event(db, config, terminal, item):
                mirrored += 1
            cursor = max(cursor, int(log_id))
        config.external_last_log_id = cursor
        config.external_last_sync_at = datetime.now(timezone.utc)
        config.external_sync_error = None
        db.commit()
        if len(rows) < batch_size:
            break
    if any(unresolved.values()):
        logger.warning(
            "Unresolved external perimeter batch summary factory=%s enter=%s exit=%s",
            config.factory_code, unresolved["ENTER"], unresolved["EXIT"],
        )
    config.external_last_sync_at = datetime.now(timezone.utc)
    config.external_sync_error = None
    db.commit()
    return mirrored


def external_current_states(*, max_log_id: int | None = None, query=None) -> list[dict]:
    """Return the latest resolvable real movement per badge through one SQL cursor."""
    if max_log_id is None:
        max_log_id = external_high_watermark()
    if query is not None:
        rows = query(max_log_id)
    else:
        connection = _connect()
        try:
            rows = connection.cursor().execute(_CURRENT_STATES_SQL, int(max_log_id)).fetchall()
        except Exception as exc:
            raise ExternalPerimeterError(_safe_odbc_category(exc, phase="query")) from None
        finally:
            connection.close()

    latest: dict[str, dict] = {}
    unresolved = {"ENTER": 0, "EXIT": 0}
    for row in rows:
        item = _normalize_external_row(row)
        if item.get("log_id") is None or item.get("event_time") is None:
            continue
        if not item.get("reporter_id"):
            direction = "ENTER" if item.get("zone_code") == 2 else "EXIT"
            unresolved[direction] += 1
            logger.warning("Unresolved external perimeter reconciliation movement log_id=%s direction=%s",
                           item["log_id"], direction)
            continue
        badge = item["reporter_id"]
        previous = latest.get(badge)
        if previous is None or (item["log_id"], item["event_time"]) > (previous["log_id"], previous["event_time"]):
            latest[badge] = item
    if any(unresolved.values()):
        logger.warning("Unresolved external perimeter reconciliation totals enter=%s exit=%s",
                       unresolved["ENTER"], unresolved["EXIT"])
    return list(latest.values())


def reconcile_external_factory(db: Session, config: FactoryPerimeterSettings) -> int:
    """Repair divergent local states from authoritative SECURITY_DB current state."""
    if not config.enabled or config.badge_source != "EXTERNAL":
        return 0
    high_watermark = external_high_watermark()
    sql_by_badge = {
        item["reporter_id"]: item
        for item in external_current_states(max_log_id=high_watermark)
    }
    local_events = db.scalars(
        select(FactoryPerimeterEvent)
        .where(FactoryPerimeterEvent.factory_code == config.factory_code)
        .order_by(FactoryPerimeterEvent.event_datetime.desc(), FactoryPerimeterEvent.id.desc())
    ).all()
    local_by_badge: dict[str, FactoryPerimeterEvent] = {}
    for event in local_events:
        local_by_badge.setdefault(event.reporter_id, event)

    # Do not materialize outside-only badges. Reconcile only known local occupants
    # and current SQL occupants that need an ENTER snapshot.
    relevant = {
        badge for badge, item in sql_by_badge.items() if item["zone_code"] == 2
    } | {
        badge for badge, event in local_by_badge.items() if event.direction == "ENTER"
    }
    terminal = ensure_virtual_terminal(db, config.factory_code)
    repaired = 0
    for badge in relevant:
        sql_item = sql_by_badge.get(badge)
        local_event = local_by_badge.get(badge)
        sql_inside = sql_item is not None and sql_item["zone_code"] == 2
        local_inside = local_event is not None and local_event.direction == "ENTER"
        if sql_inside == local_inside:
            continue
        if sql_item is None:
            # Without an authoritative resolvable state, preserve local state.
            logger.warning("External reconciliation has no resolvable SQL state badge=%s", badge)
            continue
        if mirror_external_event(db, config, terminal, sql_item):
            repaired += 1

    config.external_last_sync_at = datetime.now(timezone.utc)
    config.external_sync_error = None
    db.commit()
    logger.info(
        "External perimeter reconciliation complete factory=%s cursor=%s repaired=%s",
        config.factory_code, high_watermark, repaired,
    )
    return repaired


def reconcile_enabled_external_perimeters() -> int:
    total = 0
    with SessionLocal() as db:
        configs = db.scalars(
            select(FactoryPerimeterSettings).where(
                FactoryPerimeterSettings.enabled.is_(True),
                FactoryPerimeterSettings.badge_source == "EXTERNAL",
            )
        ).all()
        for config in configs:
            try:
                total += reconcile_external_factory(db, config)
            except ExternalPerimeterError as exc:
                db.rollback()
                fresh = db.get(FactoryPerimeterSettings, config.factory_code)
                if fresh is not None:
                    fresh.external_last_sync_at = datetime.now(timezone.utc)
                    fresh.external_sync_error = exc.category
                    db.commit()
                logger.warning("External perimeter reconciliation failed factory=%s category=%s", config.factory_code, exc.category)
            except Exception:
                db.rollback()
                fresh = db.get(FactoryPerimeterSettings, config.factory_code)
                if fresh is not None:
                    fresh.external_last_sync_at = datetime.now(timezone.utc)
                    fresh.external_sync_error = "INTERNAL_ERROR"
                    db.commit()
                logger.exception("Unexpected external perimeter reconciliation failure factory=%s", config.factory_code)
    return total


def sync_enabled_external_perimeters() -> int:
    total = 0
    with SessionLocal() as db:
        configs = db.scalars(
            select(FactoryPerimeterSettings).where(
                FactoryPerimeterSettings.enabled.is_(True),
                FactoryPerimeterSettings.badge_source == "EXTERNAL",
            )
        ).all()
        for config in configs:
            try:
                total += sync_external_factory(db, config)
            except ExternalPerimeterError as exc:
                db.rollback()
                fresh = db.get(FactoryPerimeterSettings, config.factory_code)
                if fresh is not None:
                    fresh.external_last_sync_at = datetime.now(timezone.utc)
                    fresh.external_sync_error = exc.category
                    db.commit()
                logger.warning("External perimeter replication failed factory=%s category=%s", config.factory_code, exc.category)
            except Exception:
                db.rollback()
                fresh = db.get(FactoryPerimeterSettings, config.factory_code)
                if fresh is not None:
                    fresh.external_last_sync_at = datetime.now(timezone.utc)
                    fresh.external_sync_error = "INTERNAL_ERROR"
                    db.commit()
                logger.exception("Unexpected external perimeter replication failure factory=%s", config.factory_code)
    return total
