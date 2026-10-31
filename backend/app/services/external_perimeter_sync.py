"""Incremental read-only replication of Arganda SECURITY_DB perimeter movements."""
import logging
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.domain.enums import IdentificationMethod
from app.models.perimeter import FactoryPerimeterEvent, FactoryPerimeterSettings
from app.models.terminal import Terminal
from app.models.factory import Factory
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

_OVERLAP = timedelta(minutes=15)
_SOURCE_NOW_SQL = "SELECT SYSUTCDATETIME()"
_EVENTS_AFTER_SQL = """
WITH batch AS (
    SELECT TOP ({limit}) t.id, t.unique_key, t.log_id,
           COALESCE(t.create_time, t.event_time) AS source_created_at,
           t.event_time, t.acc_zone_code, t.card_no
    FROM dbo.acc_transaction AS t
    WHERE t.acc_zone_code IN (1, 2)
      AND COALESCE(t.create_time, t.event_time) >= ?
      {cursor_predicate}
    ORDER BY COALESCE(t.create_time, t.event_time), t.id
) , page AS (
    SELECT batch.*, COUNT(*) OVER () AS source_batch_size FROM batch
)
SELECT CAST(t.id AS nvarchar(128)) AS source_transaction_id, t.unique_key, t.log_id,
       t.source_created_at, t.event_time, t.acc_zone_code, pae.attr_value4, t.source_batch_size
FROM page AS t
LEFT JOIN dbo.pers_card AS pc ON pc.card_no = t.card_no
LEFT JOIN dbo.pers_person AS p ON p.id = pc.person_id
LEFT JOIN dbo.pers_attribute_ext AS pae ON pae.person_id = p.id
ORDER BY t.source_created_at, t.id, pae.attr_value4
"""

_LATEST_BADGE_EVENT_SQL = """
SELECT TOP (1) CAST(t.id AS nvarchar(128)), t.unique_key, t.log_id,
       COALESCE(t.create_time, t.event_time), t.event_time, t.acc_zone_code
FROM dbo.pers_attribute_ext AS pae
JOIN dbo.pers_person AS p ON p.id = pae.person_id
JOIN dbo.pers_card AS pc ON pc.person_id = p.id
JOIN dbo.acc_transaction AS t ON t.card_no = pc.card_no
WHERE pae.attr_value4 = ? AND t.acc_zone_code IN (1, 2)
ORDER BY t.event_time DESC, t.id DESC
"""

_CURRENT_INSIDE_SQL = """
WITH mapped AS (
    SELECT t.id AS source_transaction_pk, CAST(t.id AS nvarchar(128)) AS source_transaction_id,
           t.unique_key, t.log_id, t.card_no,
           COALESCE(t.create_time, t.event_time) AS source_created_at, t.event_time,
           t.acc_zone_code, COUNT(DISTINCT pae.attr_value4) AS mapping_count,
           MAX(CASE WHEN pae.attr_value4 IS NULL THEN 1 ELSE 0 END) AS has_unresolved_mapping,
           MAX(pae.attr_value4) AS attr_value4
    FROM dbo.acc_transaction AS t
    LEFT JOIN dbo.pers_card AS pc ON pc.card_no = t.card_no
    LEFT JOIN dbo.pers_person AS p ON p.id = pc.person_id
    LEFT JOIN dbo.pers_attribute_ext AS pae ON pae.person_id = p.id
    WHERE t.acc_zone_code IN (1, 2)
    GROUP BY t.id, t.unique_key, t.log_id, t.card_no, COALESCE(t.create_time, t.event_time),
             t.event_time, t.acc_zone_code
), latest AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY CASE WHEN mapping_count = 1 AND has_unresolved_mapping = 0
                          THEN CAST(attr_value4 AS nvarchar(255))
                          ELSE CONCAT(N'#UNRESOLVED#', CAST(card_no AS nvarchar(255))) END
        ORDER BY event_time DESC, source_transaction_pk DESC
    ) AS rn
    FROM mapped
)
SELECT source_transaction_id, unique_key, log_id, source_created_at, event_time,
       acc_zone_code,
       CASE WHEN mapping_count <= 1 AND has_unresolved_mapping = 0 THEN attr_value4 ELSE NULL END,
       CASE WHEN mapping_count > 1 OR has_unresolved_mapping > 0 THEN 1 ELSE 0 END,
       card_no
FROM latest WHERE rn = 1 AND acc_zone_code = 2
ORDER BY event_time, source_transaction_id
"""

_CURRENT_STATES_SQL = _CURRENT_INSIDE_SQL.replace(" AND acc_zone_code = 2", "")


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


def external_source_now(*, query=None) -> datetime:
    """Return Madrid wall time for naive SQL Server create_time comparisons."""
    if query is not None:
        value = query()
    else:
        connection = _connect()
        try:
            row = connection.cursor().execute(_SOURCE_NOW_SQL).fetchone()
            value = row[0] if row else None
        except Exception as exc:
            raise ExternalPerimeterError(_safe_odbc_category(exc, phase="query")) from None
        finally:
            connection.close()
    if not isinstance(value, datetime):
        raise ExternalPerimeterError("INVALID_RESPONSE")
    # SQL Server clock is UTC; source create_time is stored as Madrid naive wall time.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo(settings.event_timezone)).replace(tzinfo=None)


def _normalize_external_row(row, *, reporter_id: str | None = None) -> dict:
    try:
        if len(row) >= 7:
            transaction_id, unique_key, raw_log_id, source_created_at, event_time, raw_zone, attr_value = row[:7]
            if len(row) >= 10:
                source_batch_size = None
                mapping_ambiguous = bool(row[8])
                source_card_no = row[9]
            elif len(row) == 9:
                source_batch_size = None
                mapping_ambiguous = bool(row[8])
                source_card_no = row[8]
            else:
                source_batch_size = int(row[7]) if len(row) == 8 and row[7] is not None else None
                mapping_ambiguous = False
                source_card_no = None
        else:  # retained for callers representing local reconciliation snapshots
            raw_log_id, event_time, raw_zone = row[:3]
            transaction_id = unique_key = source_created_at = None
            attr_value = row[3] if len(row) > 3 else None
            mapping_ambiguous = False
            source_card_no = None
            source_batch_size = None
        log_id = int(raw_log_id) if raw_log_id is not None else None
        zone_code = int(raw_zone)
    except (TypeError, ValueError, IndexError):
        return {"source_transaction_id": None, "unique_key": None, "log_id": None,
                "source_created_at": None, "event_time": None, "zone_code": None,
                "reporter_id": reporter_id}
    if not isinstance(event_time, datetime) or zone_code not in (1, 2):
        return {"source_transaction_id": str(transaction_id) if transaction_id is not None else None,
                "unique_key": unique_key, "log_id": log_id, "source_created_at": source_created_at,
                "event_time": None, "zone_code": zone_code, "reporter_id": reporter_id}
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=ZoneInfo(settings.event_timezone))
    if reporter_id is None and attr_value is not None:
        try:
            reporter_id = attr_value_to_reader_number(str(attr_value))
        except ValueError:
            reporter_id = None
    result = {
        "source_transaction_id": str(transaction_id) if transaction_id is not None else None,
        "unique_key": str(unique_key) if unique_key is not None else None,
        "log_id": log_id,
        "source_created_at": source_created_at,
        "event_time": event_time,
        "zone_code": zone_code,
        "reporter_id": reporter_id,
    }
    if len(row) == 8 and row[7] is not None:
        result["_source_batch_size"] = source_batch_size
    if len(row) >= 9:
        result["_mapping_ambiguous"] = mapping_ambiguous
        result["source_card_no"] = source_card_no
    return result


def external_events_after(
    window_from: datetime,
    after_created_at: datetime | None = None,
    after_transaction_id: str | None = None,
    *, limit: int | None = None, query=None,
) -> list[dict]:
    batch_size = max(1, min(int(limit or settings.perimeter_external_sync_batch_size), 1000))
    if query is not None:
        rows = query(window_from, after_created_at, after_transaction_id, batch_size)
    else:
        connection = _connect()
        try:
            cursor_predicate = ""
            params = [window_from]
            if after_created_at is not None and after_transaction_id is not None:
                cursor_predicate = (
                    "AND (COALESCE(t.create_time, t.event_time) > ? "
                    "OR (COALESCE(t.create_time, t.event_time) = ? "
                    "AND t.id > ?))"
                )
                params.extend([after_created_at, after_created_at, after_transaction_id])
            sql = _EVENTS_AFTER_SQL.format(limit=batch_size, cursor_predicate=cursor_predicate)
            rows = connection.cursor().execute(sql, *params).fetchall()
        except Exception as exc:
            raise ExternalPerimeterError(_safe_odbc_category(exc, phase="query")) from None
        finally:
            connection.close()
    by_transaction: dict[str, list[dict]] = {}
    source_batch_count_available = any(len(row) == 8 and row[7] is not None for row in rows)
    for row in rows:
        item = _normalize_external_row(row)
        source_id = item.get("source_transaction_id")
        if source_id:
            by_transaction.setdefault(str(source_id), []).append(item)
    result = []
    source_batch_size = max(
        (item.get("_source_batch_size") for items in by_transaction.values() for item in items
         if item.get("_source_batch_size") is not None), default=None,
    )
    for source_id, items in by_transaction.items():
        badges = {item.get("reporter_id") for item in items if item.get("reporter_id")}
        representative = dict(items[0])
        if len({(item["event_time"], item["zone_code"], item.get("unique_key")) for item in items}) > 1:
            representative["reporter_id"] = None
            representative["_mapping_ambiguous"] = True
        has_unresolved_mapping = any(not item.get("reporter_id") for item in items)
        is_ambiguous = any(item.get("_mapping_ambiguous") for item in items)
        representative.pop("_mapping_ambiguous", None)
        if len(badges) > 1 or (badges and (has_unresolved_mapping or is_ambiguous)):
            representative["reporter_id"] = None
            representative["_mapping_ambiguous"] = True
            logger.warning(
                "Ambiguous external perimeter mapping source_transaction_id=%s mapped_badges=%s unresolved_rows=%s",
                source_id, len(badges), has_unresolved_mapping,
            )
        elif len(badges) == 1:
            representative["reporter_id"] = next(iter(badges))
        result.append(representative)
    def source_order(item: dict) -> tuple[datetime, int | str]:
        created = item.get("source_created_at") or item.get("event_time")
        source_id = item.get("source_transaction_id") or ""
        try:
            key: int | str = int(source_id)
        except (TypeError, ValueError):
            key = source_id
        return created, key
    ordered = sorted(result, key=source_order)
    for item in ordered:
        item.pop("_source_batch_size", None)
        if source_batch_count_available:
            item["_page_full"] = (
                source_batch_size >= batch_size
            )
    return ordered


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
    item = _normalize_external_row((*row, None), reporter_id=badge)
    item["reporter_id"] = badge
    return item


def external_inside_snapshot(max_log_id: int | None = None, *, query=None) -> list[dict]:
    """Return one current INSIDE snapshot per external badge, without importing history."""
    if query is not None:
        rows = query(max_log_id)
    else:
        connection = _connect()
        try:
            rows = connection.cursor().execute(_CURRENT_INSIDE_SQL).fetchall()
        except Exception as exc:
            raise ExternalPerimeterError(_safe_odbc_category(exc, phase="query")) from None
        finally:
            connection.close()
    items = [_normalize_external_row(row) for row in rows]
    sql_snapshot_shape = any(len(row) >= 10 for row in rows)
    ambiguous_cards = {str(item.get("source_card_no")) for item in items
                       if item.get("_mapping_ambiguous") and item.get("source_card_no") is not None}
    resolved = [item for item in items
                if item.get("zone_code") == 2 and item.get("reporter_id")
                and not item.get("_mapping_ambiguous")
                and (item.get("source_card_no") is None or str(item["source_card_no"]) not in ambiguous_cards)]
    for item in resolved:
        item.pop("source_card_no", None)
        item.pop("_mapping_ambiguous", None)
    if not sql_snapshot_shape:
        for item in resolved:
            item.pop("_source_batch_size", None)
    return resolved


def _virtual_terminal_code(factory_code: str) -> str:
    return f"EXT-{factory_code}"[:64]


def _virtual_device_id(factory_code: str) -> str:
    return f"EXTERNAL-PERIMETER-{factory_code}"[:128]


def ensure_virtual_terminal(db: Session, factory_code: str) -> Terminal:
    factory = db.scalar(select(Factory).where(Factory.code == factory_code))
    if factory is None:
        raise ValueError("External perimeter factory does not exist")
    if not factory.active:
        raise ValueError("External perimeter factory is inactive")
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
    """Prefer the source transaction PK; legacy snapshots retain stable badge IDs."""
    source_id = item.get("source_transaction_id")
    if source_id:
        return str(uuid5(NAMESPACE_URL, f"bss-timecollection:{factory_code}:{SOURCE}:transaction:{source_id}"))
    log_id = item.get("log_id")
    badge = item.get("reporter_id")
    if log_id is not None and int(log_id) > 0:
        return _external_event_uuid(factory_code, int(log_id))
    return str(uuid5(NAMESPACE_URL, f"bss-timecollection:{factory_code}:{SOURCE}:snapshot:{badge}"))


def _external_correlation_uuid(factory_code: str, log_id: int) -> str:
    return str(uuid5(NAMESPACE_URL, f"bss-timecollection:{factory_code}:{SOURCE}:correlation:{log_id}"))


def _transaction_correlation_uuid(factory_code: str, item: dict) -> str:
    source_id = item.get("source_transaction_id")
    if source_id:
        return str(uuid5(NAMESPACE_URL, f"bss-timecollection:{factory_code}:{SOURCE}:correlation:transaction:{source_id}"))
    return _external_correlation_uuid(factory_code, int(item.get("log_id") or 0))


def mirror_external_event(
    db: Session,
    config: FactoryPerimeterSettings,
    terminal: Terminal,
    item: dict,
) -> bool:
    log_id = item.get("log_id")
    source_id = item.get("source_transaction_id")
    source_id = str(source_id) if source_id is not None else None
    event_time = item.get("event_time")
    zone_code = item.get("zone_code")
    badge = item.get("reporter_id")
    if (log_id is None and not source_id) or event_time is None or zone_code not in (1, 2) or not badge:
        return False

    event_id = _snapshot_event_uuid(config.factory_code, item)
    if db.get(FactoryPerimeterEvent, event_id) is not None:
        return False

    # Source identity is authoritative even when an older mirror has a legacy
    # log_id-derived UUID. This also makes retries safe after legacy adoption.
    if source_id and db.scalar(
        select(FactoryPerimeterEvent.id).where(
            FactoryPerimeterEvent.factory_code == config.factory_code,
            FactoryPerimeterEvent.source_system == SOURCE,
            FactoryPerimeterEvent.source_transaction_id == source_id,
        ).limit(1)
    ) is not None:
        return False

    # Claim a legacy row only when every observable attribute matches. Afterward,
    # other source transactions with the same log_id receive their own PK-based ID.
    if source_id and log_id is not None:
        legacy_id = _external_event_uuid(config.factory_code, int(log_id))
        legacy = db.get(FactoryPerimeterEvent, legacy_id)
        legacy_time = legacy.event_datetime if legacy is not None else None
        if legacy_time is not None and legacy_time.tzinfo is None:
            legacy_time = legacy_time.replace(tzinfo=ZoneInfo(settings.event_timezone))
        expected_direction = "EXIT" if zone_code == 1 else "ENTER"
        if (legacy is not None and legacy.source_transaction_id is None
                and legacy.reporter_id == badge and legacy.direction == expected_direction
                and legacy_time.astimezone(timezone.utc) == event_time.astimezone(timezone.utc)):
            correlation_id = _transaction_correlation_uuid(config.factory_code, item)
            legacy.source_system = SOURCE
            legacy.source_transaction_id = str(source_id)
            legacy.source_log_id = log_id
            legacy.source_unique_key = item.get("unique_key")
            legacy.correlation_id = correlation_id
            if legacy.auto_cell_exit_event_id:
                cell_event = db.get(TimeEvent, legacy.auto_cell_exit_event_id)
                if cell_event is not None:
                    cell_event.correlation_id = correlation_id
            return False

    direction = "EXIT" if zone_code == 1 else "ENTER"
    correlation_id = _transaction_correlation_uuid(config.factory_code, item)
    auto_event = None
    if direction == "EXIT":
        now_utc = datetime.now(timezone.utc)
        aware_event_time = event_time
        if aware_event_time.tzinfo is None:
            aware_event_time = aware_event_time.replace(tzinfo=ZoneInfo(settings.event_timezone))
        if aware_event_time.astimezone(timezone.utc) <= now_utc:
            auto_event = create_auto_cell_exit_for_factory_exit(
                db,
                config,
                config.factory_code,
                badge,
                IdentificationMethod.RFID,
                aware_event_time,
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
            source_system=SOURCE if source_id else None,
            source_transaction_id=source_id,
            source_log_id=log_id,
            source_unique_key=item.get("unique_key"),
            auto_cell_exit_event_id=auto_event.id if auto_event else None,
        )
    )
    return True


def _bootstrap_external_factory(db: Session, config: FactoryPerimeterSettings, terminal: Terminal) -> int:
    source_now = external_source_now()
    snapshots = external_inside_snapshot()
    mirrored = 0
    for item in snapshots:
        if mirror_external_event(db, config, terminal, item):
            mirrored += 1
    now = datetime.now(timezone.utc)
    config.external_sync_window_from = source_now - _OVERLAP
    config.external_sync_cursor_created_at = None
    config.external_sync_cursor_transaction_id = None
    config.external_sync_initialized_at = now
    config.external_last_sync_at = now
    config.external_sync_error = None
    db.commit()
    logger.info(
        "External perimeter replication initialized factory=%s inside_snapshots=%s",
        config.factory_code,
        mirrored,
    )
    return mirrored


def sync_external_factory(db: Session, config: FactoryPerimeterSettings) -> int:
    if not config.enabled or config.badge_source != "EXTERNAL":
        return 0
    terminal = ensure_virtual_terminal(db, config.factory_code)
    if config.external_sync_initialized_at is None:
        return _bootstrap_external_factory(db, config, terminal)

    mirrored = 0
    unresolved = {"ENTER": 0, "EXIT": 0}
    source_now = external_source_now()
    if config.external_sync_window_from is None:
        last_sync = config.external_last_sync_at
        if last_sync is not None:
            if last_sync.tzinfo is None:
                last_sync = last_sync.replace(tzinfo=timezone.utc)
            last_sync_local = last_sync.astimezone(ZoneInfo(settings.event_timezone)).replace(tzinfo=None)
            config.external_sync_window_from = last_sync_local - _OVERLAP
        else:
            config.external_sync_window_from = source_now - _OVERLAP
    window_from = config.external_sync_window_from
    after_created_at = config.external_sync_cursor_created_at
    after_transaction_id = config.external_sync_cursor_transaction_id
    batch_size = max(1, min(int(settings.perimeter_external_sync_batch_size), 1000))
    exhausted_window = False
    for _ in range(10):
        rows = external_events_after(
            window_from, after_created_at, after_transaction_id, limit=batch_size,
        )
        if not rows:
            exhausted_window = True
            break
        for item in rows:
            log_id = item.get("log_id")
            source_id = item.get("source_transaction_id")
            created_at = item.get("source_created_at")
            if not source_id:
                continue
            if not item.get("reporter_id"):
                direction = "ENTER" if item.get("zone_code") == 2 else "EXIT"
                logger.warning(
                    "Unresolved external perimeter movement factory=%s source_transaction_id=%s log_id=%s direction=%s",
                    config.factory_code, source_id, log_id, direction,
                )
                unresolved[direction] += 1
            if mirror_external_event(db, config, terminal, item):
                mirrored += 1
            if created_at is not None:
                after_created_at = created_at
                after_transaction_id = source_id
        config.external_sync_cursor_created_at = after_created_at
        config.external_sync_cursor_transaction_id = after_transaction_id
        config.external_last_sync_at = datetime.now(timezone.utc)
        config.external_sync_error = None
        db.commit()
        page_full = any(item.get("_page_full") for item in rows)
        if not page_full:
            exhausted_window = True
            break
    if any(unresolved.values()):
        logger.warning(
            "Unresolved external perimeter batch summary factory=%s enter=%s exit=%s",
            config.factory_code, unresolved["ENTER"], unresolved["EXIT"],
        )
    if exhausted_window:
        config.external_sync_window_from = source_now - _OVERLAP
        config.external_sync_cursor_created_at = None
        config.external_sync_cursor_transaction_id = None
    config.external_last_sync_at = datetime.now(timezone.utc)
    config.external_sync_error = None
    db.commit()
    return mirrored


def external_current_states(*, query=None) -> list[dict]:
    """Return the latest resolvable real movement per badge from SECURITY_DB."""
    if query is not None:
        rows = query()
    else:
        connection = _connect()
        try:
            rows = connection.cursor().execute(_CURRENT_STATES_SQL).fetchall()
        except Exception as exc:
            raise ExternalPerimeterError(_safe_odbc_category(exc, phase="query")) from None
        finally:
            connection.close()

    candidates: list[dict] = []
    ambiguous_card_numbers: set[str] = set()
    unresolved = {"ENTER": 0, "EXIT": 0}
    sql_state_shape = any(len(row) >= 9 for row in rows)
    for row in rows:
        item = _normalize_external_row(row)
        if (item.get("log_id") is None and item.get("source_transaction_id") is None) or item.get("event_time") is None:
            continue
        if item.get("_mapping_ambiguous"):
            if item.get("source_card_no") is not None:
                ambiguous_card_numbers.add(str(item["source_card_no"]))
            direction = "ENTER" if item.get("zone_code") == 2 else "EXIT"
            unresolved[direction] += 1
            continue
        if not item.get("reporter_id"):
            direction = "ENTER" if item.get("zone_code") == 2 else "EXIT"
            unresolved[direction] += 1
            continue
        candidates.append(item)

    candidates = [item for item in candidates
                  if item.get("source_card_no") is None
                  or str(item["source_card_no"]) not in ambiguous_card_numbers]

    by_source_id: dict[str, list[dict]] = {}
    for item in candidates:
        by_source_id.setdefault(item.get("source_transaction_id") or f"legacy:{item['log_id']}", []).append(item)
    ambiguous_ids: set[str] = set()
    for source_id, items in by_source_id.items():
        badges = {item["reporter_id"] for item in items}
        if len(badges) > 1 or (badges and any(item.get("_mapping_ambiguous") for item in items)):
            ambiguous_ids.add(source_id)
            direction = "ENTER" if items[0]["zone_code"] == 2 else "EXIT"
            unresolved[direction] += 1

    latest: dict[str, dict] = {}
    conflicted: set[str] = set()
    for item in candidates:
        source_id = item.get("source_transaction_id") or f"legacy:{item['log_id']}"
        if source_id in ambiguous_ids:
            continue
        badge = item["reporter_id"]
        previous = latest.get(badge)
        def source_pk(value: dict) -> int:
            try:
                return int(value.get("source_transaction_id"))
            except (TypeError, ValueError):
                return int(value.get("log_id") or 0)
        if previous is None or (item["event_time"], source_pk(item)) > (
            previous["event_time"], source_pk(previous)
        ):
            latest[badge] = item
        elif (item["event_time"], source_pk(item)) == (
            previous["event_time"], source_pk(previous)
        ) and (item["zone_code"] != previous["zone_code"]
              or item.get("unique_key") != previous.get("unique_key")):
            conflicted.add(badge)
    for badge in conflicted:
        latest.pop(badge, None)
    if any(unresolved.values()):
        logger.warning("Unresolved external perimeter reconciliation totals enter=%s exit=%s",
                       unresolved["ENTER"], unresolved["EXIT"])
    result = list(latest.values())
    if not sql_state_shape:
        for item in result:
            item.pop("_mapping_ambiguous", None)
            item.pop("source_card_no", None)
    return result


def reconcile_external_factory(
    db: Session,
    config: FactoryPerimeterSettings,
) -> int:
    """Repair divergent local states from authoritative SECURITY_DB current state."""
    if not config.enabled or config.badge_source != "EXTERNAL":
        return 0
    sql_by_badge = {
        item["reporter_id"]: item
        for item in external_current_states()
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
        "External perimeter reconciliation complete factory=%s repaired=%s",
        config.factory_code, repaired,
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
