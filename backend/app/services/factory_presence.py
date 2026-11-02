"""Reconcile current physical factory presence independently of movement history."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import logging
from typing import Callable
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.perimeter import FactoryPerimeterEvent, FactoryPerimeterSettings, FactoryPresenceProjection, TerminalBadgeRead
from app.models.person_badge_assignment import PersonBadgeAssignment
from app.models.time_event import TimeEvent
from app.services.external_perimeter import ExternalPerimeterError, _connection_string, _credentials, _safe_odbc_category
from app.services.person_identity import (
    PersonIdentity, PersonIdentityError, _CURRENT_SQL, _RESOLVE_SQL,
    _attr_value_to_reader_number, _normalize_row, fetch_current_person_badges,
    resolve_person_identity,
)
from app.services.external_perimeter import reader_number_to_attr_value

logger = logging.getLogger(__name__)
SOURCE = "SQLSERVER_SECURITY_DB"

_CURRENT_CREDENTIALS_SQL = """
SELECT p.id, p.pin, pc.id, pc.card_no, pc.person_pin
FROM dbo.pers_person AS p
JOIN dbo.pers_card AS pc ON pc.person_id = p.id
WHERE p.pin = ? AND pc.card_state = 1
  AND (pc.start_time IS NULL OR pc.start_time <= GETDATE())
  AND (pc.end_time IS NULL OR pc.end_time > GETDATE())
ORDER BY pc.id
"""
_PRESENCE_CURRENT_IDENTITIES_SQL = """
SELECT pae.attr_value4, p.id, p.pin, pc.id, pc.card_no, pc.person_pin
FROM dbo.pers_person AS p
JOIN dbo.pers_card AS pc ON pc.person_id = p.id
LEFT JOIN dbo.pers_attribute_ext AS pae ON pae.person_id = p.id
WHERE pc.card_state = 1
  AND (pc.start_time IS NULL OR pc.start_time <= GETDATE())
  AND (pc.end_time IS NULL OR pc.end_time > GETDATE())
ORDER BY p.id, pc.id, pae.attr_value4
"""
_LATEST_CARD_MOVEMENT_SQL = """
SELECT TOP (1) CAST(t.id AS nvarchar(128)), t.event_time, t.acc_zone_code
FROM dbo.acc_transaction AS t
WHERE t.card_no = ? AND t.acc_zone_code IN (1, 2)
ORDER BY t.event_time DESC, t.id DESC
"""
_LATEST_CURRENT_CARD_MOVEMENTS_SQL = """
WITH current_cards AS (
    SELECT DISTINCT pc.card_no
    FROM dbo.pers_card AS pc
    WHERE pc.card_state = 1
      AND (pc.start_time IS NULL OR pc.start_time <= GETDATE())
      AND (pc.end_time IS NULL OR pc.end_time > GETDATE())
), latest AS (
    SELECT t.card_no, CAST(t.id AS nvarchar(128)) AS transaction_id,
           t.event_time, t.acc_zone_code,
           ROW_NUMBER() OVER (PARTITION BY t.card_no ORDER BY t.event_time DESC, t.id DESC) AS position
    FROM current_cards AS pc
    JOIN dbo.acc_transaction AS t ON t.card_no = pc.card_no
    WHERE t.acc_zone_code IN (1, 2)
)
SELECT card_no, transaction_id, event_time, acc_zone_code
FROM latest WHERE position = 1
"""
_NORMALIZED_READER_SQL = """
SELECT DISTINCT pae.attr_value4, p.id, p.pin, pc.id, pc.card_no, pc.person_pin
FROM dbo.pers_attribute_ext AS pae
JOIN dbo.pers_person AS p ON p.id = pae.person_id
JOIN dbo.pers_card AS pc ON pc.person_id = p.id
WHERE TRY_CONVERT(decimal(38, 0), LTRIM(RTRIM(CAST(pae.attr_value4 AS nvarchar(255))))) IN (?, ?)
"""
_CURRENT_CREDENTIAL_SQL = """
SELECT pc.id, pc.card_no, p.id
FROM dbo.pers_card AS pc
LEFT JOIN dbo.pers_person AS p ON p.id = pc.person_id
WHERE pc.card_no = ? AND pc.card_state = 1
  AND (pc.start_time IS NULL OR pc.start_time <= GETDATE())
  AND (pc.end_time IS NULL OR pc.end_time > GETDATE())
ORDER BY pc.id
"""


class PresenceSourceError(RuntimeError):
    def __init__(self, category: str):
        super().__init__(category)
        self.category = category


@dataclass
class _IdentityCandidate:
    person_id: str | None = None
    reader_ids: set[str] = field(default_factory=set)
    credential_ids: set[str] = field(default_factory=set)
    source_person_ids: set[str] = field(default_factory=set)


def _safe_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _same_value(left, right) -> bool:
    if isinstance(left, datetime) and isinstance(right, datetime):
        if left.tzinfo is None:
            left = left.replace(tzinfo=timezone.utc)
        if right.tzinfo is None:
            right = right.replace(tzinfo=timezone.utc)
        return left.astimezone(timezone.utc) == right.astimezone(timezone.utc)
    return left == right


def _candidate_key(person_id: str | None, reader_id: str | None, credential_id: str | None) -> str | None:
    if person_id:
        return f"PERSON:{person_id}"
    if reader_id:
        return f"READER:{reader_id}"
    if credential_id:
        return f"CREDENTIAL:{credential_id}"
    return None


def _collect_candidates(db: Session, factory_code: str) -> dict[str, _IdentityCandidate]:
    candidates: dict[str, _IdentityCandidate] = {}
    reader_people: dict[str, set[str]] = {}
    pin_people = {str(pin): str(pin) for (pin,) in db.execute(select(TimeEvent.person_id).join(
        TimeEvent.terminal
    ).where(TimeEvent.terminal.has(factory_code=factory_code), TimeEvent.person_id.is_not(None)).distinct())}
    assignment_rows = db.execute(select(
        PersonBadgeAssignment.person_id, PersonBadgeAssignment.reader_id,
        PersonBadgeAssignment.credential_id, PersonBadgeAssignment.source_person_id,
    ).where(PersonBadgeAssignment.factory_code == factory_code)).all()
    for row in assignment_rows:
        if row.reader_id and row.person_id:
            reader_people.setdefault(str(row.reader_id), set()).add(str(row.person_id))

    def add(person_id=None, reader_id=None, credential_id=None, source_person_id=None):
        person_id, reader_id, credential_id = map(_safe_text, (person_id, reader_id, credential_id))
        key = _candidate_key(person_id, reader_id, credential_id)
        if key is None:
            return
        item = candidates.setdefault(key, _IdentityCandidate(person_id=person_id))
        if item.person_id is None:
            item.person_id = person_id
        if reader_id:
            item.reader_ids.add(reader_id)
        if credential_id:
            item.credential_ids.add(credential_id)
        if source_person_id and _safe_text(source_person_id):
            item.source_person_ids.add(_safe_text(source_person_id))

    for row in assignment_rows:
        add(row.person_id, row.reader_id, row.credential_id, row.source_person_id)

    for row in db.scalars(select(TerminalBadgeRead).where(TerminalBadgeRead.factory_code == factory_code)):
        person = row.reporter_id.removeprefix("person:") if row.reporter_id.startswith("person:") else pin_people.get(row.reporter_id)
        if person:
            add(person)
        else:
            # Older TerminalBadgeRead rows predate stable person locking and do
            # not retain identification_method. Do not reinterpret an unknown
            # reporter (which may be a KEYPAD Employee ID) as an RFID Reader ID.
            candidates.setdefault(f"LEGACY:{row.reporter_id}", _IdentityCandidate())

    for row in db.execute(select(
        TimeEvent.person_id, TimeEvent.reporter_id, TimeEvent.credential_id,
        TimeEvent.source_person_id, TimeEvent.identification_method,
    ).join(TimeEvent.terminal).where(TimeEvent.terminal.has(factory_code=factory_code))):
        method = row.identification_method
        reader = row.reporter_id if method == "RFID" else None
        person = row.person_id or (next(iter(reader_people[reader])) if reader and len(reader_people.get(reader, ())) == 1 else None)
        add(person, reader, row.credential_id, row.source_person_id)

    for row in db.execute(select(
        FactoryPerimeterEvent.person_id, FactoryPerimeterEvent.reporter_id,
        FactoryPerimeterEvent.credential_id, FactoryPerimeterEvent.source_person_id,
    ).where(FactoryPerimeterEvent.factory_code == factory_code)):
        person = row.person_id or (next(iter(reader_people[row.reporter_id])) if len(reader_people.get(row.reporter_id, ())) == 1 else None)
        # FactoryPerimeterEvent does not snapshot identification_method. A
        # reporter string alone therefore cannot prove it was a physical Reader
        # ID (a BOTH keypad could have supplied an Employee ID). Treat it as an
        # RFID identity only when trusted PersonBadgeAssignment history confirms
        # that exact observed Reader ID.
        reader = row.reporter_id if row.reporter_id in reader_people else None
        add(person, reader, row.credential_id, row.source_person_id)

    # Existing keys remain eligible for reconciliation, so losing the source
    # identity that supported a prior INSIDE result can explicitly become UNKNOWN.
    for row in db.scalars(select(FactoryPresenceProjection).where(
        FactoryPresenceProjection.factory_code == factory_code
    )):
        person = row.person_id
        reader = row.reader_id
        credential = row.credential_id
        key = row.tracking_key
        candidates.setdefault(key, _IdentityCandidate(person_id=person))
        if person and candidates[key].person_id is None:
            candidates[key].person_id = person
        if reader:
            candidates[key].reader_ids.add(reader)
        if credential:
            candidates[key].credential_ids.add(credential)
    return candidates


def _source_resolver_from_snapshot(cursor, identities: list[PersonIdentity], historical_credentials=()):
    """Resolve the local population from one SECURITY_DB snapshot efficiently."""
    by_reader_index: dict[str, set[PersonIdentity]] = {}
    current_by_person: dict[str, list[PersonIdentity]] = {}
    current_by_credential: dict[str, list[PersonIdentity]] = {}
    for identity in identities:
        current_by_person.setdefault(identity.person_id, []).append(identity)
        if identity.credential_id:
            current_by_credential.setdefault(identity.credential_id, []).append(identity)
        if identity.reader_id:
            by_reader_index.setdefault(identity.reader_id, set()).add(identity)
    reader_cache: dict[str, PersonIdentity | PersonIdentityError] = {}
    movement_cache: dict[str, dict | None | PresenceSourceError] = {}
    orphan_cache: dict[str, bool | PresenceSourceError] = {}

    # Check local historical credentials in batches too. Retained credentials
    # may prove card presence after their person row is gone, but an N+1 ODBC
    # lookup across old card history makes reconciliation prohibitively slow.
    old_credentials = sorted(set(historical_credentials) - set(current_by_credential))
    for offset in range(0, len(old_credentials), 400):
        chunk = old_credentials[offset:offset + 400]
        if not chunk:
            continue
        try:
            placeholders = ",".join("?" for _ in chunk)
            query = _CURRENT_CREDENTIAL_SQL.replace("WHERE pc.card_no = ?", f"WHERE pc.card_no IN ({placeholders})")
            rows = cursor.execute(query, *chunk).fetchall()
            grouped: dict[str, set[tuple[str | None, str | None, str | None]]] = {}
            for row in rows:
                card_no = _safe_text(row[1])
                if card_no:
                    grouped.setdefault(card_no, set()).add((_safe_text(row[0]), card_no, _safe_text(row[2])))
            for credential in chunk:
                values = grouped.get(credential, set())
                orphan_cache[credential] = len(values) == 1 and next(iter(values))[2] is None
        except Exception as exc:
            error = PresenceSourceError(_safe_odbc_category(exc, phase="query"))
            for credential in chunk:
                orphan_cache[credential] = error

    # Resolve the latest movement for all current credentials in one indexed
    # SECURITY_DB query. Per-card round trips made a full reconciliation scale
    # with the number of employees and could take several minutes.
    try:
        movement_rows = cursor.execute(_LATEST_CURRENT_CARD_MOVEMENTS_SQL).fetchall()
        for row in movement_rows:
            credential = _safe_text(row[0])
            if not credential:
                continue
            zone = int(row[3])
            when = row[2]
            if zone not in (1, 2) or not isinstance(when, datetime):
                movement_cache[credential] = None
                continue
            if when.tzinfo is None:
                when = when.replace(tzinfo=ZoneInfo(settings.event_timezone))
            age = datetime.now(timezone.utc) - when.astimezone(timezone.utc)
            if age < -timedelta(seconds=60):
                state = "UNKNOWN"
            elif zone == 1:
                state = "OUTSIDE"
            elif age > timedelta(hours=settings.perimeter_external_max_age_hours):
                state = "UNKNOWN"
            else:
                state = "INSIDE"
            movement_cache[credential] = {
                "state": state, "at": when, "transaction_id": _safe_text(row[1]),
            }
    except Exception as exc:
        error = PresenceSourceError(_safe_odbc_category(exc, phase="query"))
        for identity in identities:
            if identity.credential_id:
                movement_cache[identity.credential_id] = error

    def by_reader(reader_id: str) -> PersonIdentity:
        result = reader_cache.get(reader_id)
        if isinstance(result, PersonIdentityError):
            raise result
        if result is not None:
            return result
        indexed = by_reader_index.get(reader_id, set())
        if len(indexed) == 1:
            first = next(iter(indexed))
            result = PersonIdentity(first.source_person_id, first.person_id, None, None, reader_id)
        elif len(indexed) > 1:
            people = {item.person_id for item in indexed}
            sources = {item.source_person_id for item in indexed}
            if len(people) == 1 and len(sources) == 1:
                first = next(iter(indexed))
                result = PersonIdentity(first.source_person_id, first.person_id, None, None, reader_id)
            else:
                result = PersonIdentityError("AMBIGUOUS_IDENTITY")
        else:
            result = PersonIdentityError("IDENTITY_NOT_FOUND")
        reader_cache[reader_id] = result
        if isinstance(result, Exception):
            raise result
        return result

    def current_credentials(person_id: str) -> list[PersonIdentity]:
        return current_by_person.get(person_id, [])

    def current_orphan_credential(credential_id: str) -> bool:
        if credential_id in orphan_cache:
            result = orphan_cache[credential_id]
            if isinstance(result, Exception):
                raise result
            return result
        try:
            rows = cursor.execute(_CURRENT_CREDENTIAL_SQL, credential_id).fetchall()
        except Exception as exc:
            error = PresenceSourceError(_safe_odbc_category(exc, phase="query"))
            orphan_cache[credential_id] = error
            raise error from None
        unique = {(_safe_text(row[0]), _safe_text(row[1]), _safe_text(row[2])) for row in rows if row[0] and row[1]}
        result = len(unique) == 1 and next(iter(unique))[2] is None
        orphan_cache[credential_id] = result
        return result

    def latest_movement(credential_id: str):
        if credential_id not in movement_cache:
            try:
                movement_cache[credential_id] = _movement(cursor, credential_id)
            except PresenceSourceError as exc:
                movement_cache[credential_id] = exc
        result = movement_cache[credential_id]
        if isinstance(result, Exception):
            raise result
        return result

    latest_movement.current_orphan_credential = current_orphan_credential
    return by_reader, current_credentials, latest_movement, current_orphan_credential


def _connect():
    try:
        import pyodbc
    except ImportError:
        raise PresenceSourceError("ODBC_DRIVER_UNAVAILABLE") from None
    try:
        return pyodbc.connect(_connection_string(_credentials()), timeout=3, autocommit=True)
    except ExternalPerimeterError as exc:
        raise PresenceSourceError(exc.category) from None
    except Exception as exc:
        raise PresenceSourceError(_safe_odbc_category(exc, phase="connect")) from None


def _identity_from_person_row(row) -> PersonIdentity | None:
    try:
        source_id, pin, card_id, card_no, person_pin = (_safe_text(value) for value in row[:5])
    except (TypeError, IndexError):
        return None
    if not all((source_id, pin, card_id, card_no, person_pin)) or pin != person_pin:
        return None
    return PersonIdentity(source_id, pin, card_id, card_no, None)


def _movement(cursor, credential_id: str) -> dict | None:
    try:
        row = cursor.execute(_LATEST_CARD_MOVEMENT_SQL, credential_id).fetchone()
    except Exception as exc:
        raise PresenceSourceError(_safe_odbc_category(exc, phase="query")) from None
    if row is None:
        return None
    try:
        zone = int(row[2])
        when = row[1]
        if zone not in (1, 2) or not isinstance(when, datetime):
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=ZoneInfo(settings.event_timezone))
        # Match the existing external-presence policy: an EXIT remains reliable
        # evidence of OUTSIDE, while an old ENTER cannot prove someone is still
        # inside indefinitely. In particular, historical movement alone must
        # eventually resolve to UNKNOWN.
        age = datetime.now(timezone.utc) - when.astimezone(timezone.utc)
        if age < -timedelta(seconds=60):
            return None
        state = "OUTSIDE" if zone == 1 else (
            "UNKNOWN" if age > timedelta(hours=settings.perimeter_external_max_age_hours)
            else "INSIDE"
        )
        return {"state": state, "at": when,
                "transaction_id": _safe_text(row[0])}
    except (TypeError, ValueError, IndexError):
        return None


def _source_resolver(cursor):
    reader_cache: dict[str, PersonIdentity | PersonIdentityError] = {}
    person_cache: dict[str, list[PersonIdentity] | PresenceSourceError] = {}
    movement_cache: dict[str, dict | None | PresenceSourceError] = {}
    orphan_cache: dict[str, bool | PresenceSourceError] = {}

    def by_reader(reader_id: str) -> PersonIdentity:
        if reader_id in reader_cache:
            result = reader_cache[reader_id]
            if isinstance(result, Exception):
                raise result
            return result
        try:
            result = resolve_person_identity(reader_id, query=lambda raw, converted: cursor.execute(
                _RESOLVE_SQL, raw, converted
            ).fetchall())
            reader_cache[reader_id] = result
            return result
        except PersonIdentityError as exc:
            if exc.category != "IDENTITY_NOT_FOUND":
                # The shared RFID resolver intentionally returns an ambiguous
                # result when one reader joins to several card rows. Presence
                # can still safely use that reader as *person lineage* when all
                # valid rows point to one person; the separate current-card
                # lookup below then requires exactly one current credential.
                # Never do this if card rows point at multiple people or any
                # matching row has inconsistent identity data.
                if exc.category == "AMBIGUOUS_IDENTITY":
                    try:
                        digits = str(reader_id).strip()
                        if not digits or not digits.isascii() or not digits.isdecimal():
                            raise ValueError
                        number = int(digits)
                        if number >= 2**32:
                            raise ValueError
                        raw, converted = digits, reader_number_to_attr_value(digits)
                        rows = cursor.execute(_RESOLVE_SQL, raw, converted).fetchall()
                        identities = set()
                        invalid = False
                        for row in rows:
                            if _safe_text(row[0]) not in {raw, converted}:
                                continue
                            identity = _normalize_row(row[1:], reader_id=digits)
                            if identity is None:
                                invalid = True
                            else:
                                identities.add(identity)
                        people = {identity.person_id for identity in identities}
                        if identities and len(people) == 1 and len(source_people := {
                            identity.source_person_id for identity in identities
                        }) == 1 and not invalid:
                            person_id = next(iter(people))
                            result = PersonIdentity(
                                next(iter(source_people)),
                                person_id, None, None, digits,
                            )
                            reader_cache[reader_id] = result
                            return result
                    except Exception:
                        pass
                reader_cache[reader_id] = exc
                raise
        digits = str(reader_id).strip()
        if not digits or not digits.isascii() or not digits.isdecimal():
            raise PersonIdentityError("IDENTITY_NOT_FOUND") from None
        try:
            number = int(digits)
            if number >= 2**32:
                raise ValueError
            candidates = {str(number), str(int(reader_number_to_attr_value(digits)))}
            params = sorted(candidates)
            if len(params) == 1:
                params.append(params[0])
            rows = cursor.execute(_NORMALIZED_READER_SQL, *params).fetchall()
        except ValueError:
            error = PersonIdentityError("IDENTITY_NOT_FOUND")
            reader_cache[reader_id] = error
            raise error from None
        except Exception as exc:
            error = PersonIdentityError("QUERY_FAILED")
            reader_cache[reader_id] = error
            raise error from None
        matches: set[PersonIdentity] = set()
        for row in rows:
            raw = _safe_text(row[0])
            if not raw or not raw.isascii() or not raw.isdecimal() or str(int(raw)) not in candidates:
                continue
            identity = _identity_from_person_row(row[1:])
            if identity is not None:
                matches.add(identity)
        if not matches:
            error = PersonIdentityError("IDENTITY_NOT_FOUND")
            reader_cache[reader_id] = error
            raise error
        if len(matches) != 1:
            error = PersonIdentityError("AMBIGUOUS_IDENTITY")
            reader_cache[reader_id] = error
            raise error
        result = next(iter(matches))
        reader_cache[reader_id] = result
        return result

    def current_credentials(person_id: str) -> list[PersonIdentity]:
        if person_id in person_cache:
            result = person_cache[person_id]
            if isinstance(result, Exception):
                raise result
            return result
        try:
            rows = cursor.execute(_CURRENT_CREDENTIALS_SQL, person_id).fetchall()
        except Exception as exc:
            error = PresenceSourceError(_safe_odbc_category(exc, phase="query"))
            person_cache[person_id] = error
            raise error from None
        identities = [_identity_from_person_row(row) for row in rows]
        if any(identity is None for identity in identities):
            error = PresenceSourceError("INVALID_CURRENT_MAPPING")
            person_cache[person_id] = error
            raise error
        # Duplicate joins/cards are retained as separate possibilities and cause
        # fail-closed resolution in the caller.
        person_cache[person_id] = identities
        return identities

    def current_orphan_credential(credential_id: str) -> bool:
        if credential_id in orphan_cache:
            result = orphan_cache[credential_id]
            if isinstance(result, Exception):
                raise result
            return result
        try:
            rows = cursor.execute(_CURRENT_CREDENTIAL_SQL, credential_id).fetchall()
        except Exception as exc:
            error = PresenceSourceError(_safe_odbc_category(exc, phase="query"))
            orphan_cache[credential_id] = error
            raise error from None
        unique = {(_safe_text(row[0]), _safe_text(row[1]), _safe_text(row[2])) for row in rows if row[0] and row[1]}
        # A retained card is an orphan only when no current person row owns it.
        result = len(unique) == 1 and next(iter(unique))[2] is None
        orphan_cache[credential_id] = result
        return result

    def latest_movement(credential_id: str):
        if credential_id in movement_cache:
            result = movement_cache[credential_id]
            if isinstance(result, Exception):
                raise result
            return result
        try:
            result = _movement(cursor, credential_id)
        except PresenceSourceError as exc:
            movement_cache[credential_id] = exc
            raise
        movement_cache[credential_id] = result
        return result

    return by_reader, current_credentials, latest_movement, current_orphan_credential


def _expected_for_candidate(candidate: _IdentityCandidate, by_reader, current_credentials, movement):
    current_orphan_credential = getattr(movement, "current_orphan_credential", None)
    person_id = candidate.person_id
    source_person_ids = set(candidate.source_person_ids)
    reader_ids = set(candidate.reader_ids)
    credentials = set(candidate.credential_ids)
    reason = None
    resolution = "CANONICAL_PERSON"

    resolved_readers: dict[str, PersonIdentity] = {}
    ambiguous_reader = False
    for reader in sorted(reader_ids):
        try:
            resolved_readers[reader] = by_reader(reader)
        except PersonIdentityError as exc:
            if exc.category in {"AMBIGUOUS_IDENTITY", "AMBIGUOUS_CURRENT_MAPPING"}:
                ambiguous_reader = True
            continue

    resolved_people = {identity.person_id for identity in resolved_readers.values()}
    if ambiguous_reader and not person_id:
        return dict(state="UNKNOWN", person_id=person_id,
                    reader_id=next(iter(reader_ids)) if len(reader_ids) == 1 else None,
                    credential_id=None, resolution_code="AMBIGUOUS_IDENTITY",
                    unresolved_reason="AMBIGUOUS_READER_IDENTITY", movement_at=None)
    if person_id and resolved_people and resolved_people != {person_id}:
        return dict(state="UNKNOWN", person_id=person_id,
                    reader_id=next(iter(reader_ids)) if len(reader_ids) == 1 else None,
                    credential_id=None, resolution_code="AMBIGUOUS_IDENTITY",
                    unresolved_reason="PERSON_IDENTITY_CONFLICT", movement_at=None)
    if person_id is None and len(resolved_people) == 1:
        person_id = next(iter(resolved_people))
        resolution = "CURRENT_RFID_IDENTITY"
    elif person_id is None and len(resolved_people) > 1:
        return dict(state="UNKNOWN", person_id=None, reader_id=None, credential_id=None,
                    resolution_code="AMBIGUOUS_IDENTITY", unresolved_reason="AMBIGUOUS_PERSON", movement_at=None)
    elif person_id is None and ambiguous_reader:
        return dict(state="UNKNOWN", person_id=None, reader_id=None, credential_id=None,
                    resolution_code="AMBIGUOUS_IDENTITY", unresolved_reason="AMBIGUOUS_PERSON", movement_at=None)

    if person_id:
        credentials_for_person = current_credentials(person_id)
        unique = {(item.source_card_id, item.credential_id): item for item in credentials_for_person}
        if len(unique) == 0:
            if len(credentials) == 1 and current_orphan_credential and current_orphan_credential(next(iter(credentials))):
                orphan_credential = next(iter(credentials))
                orphan_state = movement(orphan_credential)
                if orphan_state is not None:
                    secondary = [dict(
                        tracking_key=f"CREDENTIAL:{orphan_credential}",
                        reader_id=next(iter(reader_ids)) if len(reader_ids) == 1 else None,
                        credential_id=orphan_credential,
                        state=orphan_state["state"],
                        resolution_code="RETAINED_CREDENTIAL",
                        unresolved_reason=("STALE_AUTHORITATIVE_MOVEMENT" if orphan_state["state"] == "UNKNOWN" else None),
                        movement_at=orphan_state["at"],
                    )]
                    if len(reader_ids) == 1:
                        secondary.append({**secondary[0], "tracking_key": f"READER:{next(iter(reader_ids))}"})
                    # Retained-card evidence may establish badge presence, but
                    # an old credential must not keep its former employee INSIDE.
                    return dict(state="UNKNOWN", person_id=person_id,
                                reader_id=next(iter(reader_ids)) if len(reader_ids) == 1 else None,
                                credential_id=None, resolution_code="CANONICAL_PERSON",
                                unresolved_reason="NO_CURRENT_CREDENTIAL", movement_at=None,
                                secondary_projections=secondary)
            if len(credentials) > 1:
                return dict(state="UNKNOWN", person_id=person_id,
                            reader_id=next(iter(reader_ids)) if len(reader_ids) == 1 else None,
                            credential_id=None, resolution_code="CANONICAL_PERSON",
                            unresolved_reason="AMBIGUOUS_HISTORICAL_CREDENTIAL", movement_at=None)
            return dict(state="UNKNOWN", person_id=person_id,
                        reader_id=next(iter(reader_ids)) if len(reader_ids) == 1 and not ambiguous_reader else None,
                        credential_id=None, resolution_code="CANONICAL_PERSON",
                        unresolved_reason="NO_CURRENT_CREDENTIAL", movement_at=None,
                        suppress_reader_projection=ambiguous_reader)
        if len(unique) > 1:
            return dict(state="UNKNOWN", person_id=person_id,
                        reader_id=next(iter(reader_ids)) if len(reader_ids) == 1 and not ambiguous_reader else None,
                        credential_id=None, resolution_code="CANONICAL_PERSON",
                        unresolved_reason="AMBIGUOUS_CURRENT_CREDENTIAL", movement_at=None,
                        suppress_reader_projection=ambiguous_reader)
        identity = next(iter(unique.values()))
        credential = identity.credential_id
        if not reader_ids:
            resolution = "CANONICAL_PERSON_CURRENT_CREDENTIAL"
        elif any(r in resolved_readers and resolved_readers[r].person_id == person_id for r in reader_ids):
            resolution = "CURRENT_RFID_IDENTITY"
        elif candidate.source_person_ids:
            resolution = "HISTORICAL_PERSON_CURRENT_CREDENTIAL"
        else:
            resolution = "CANONICAL_PERSON_CURRENT_CREDENTIAL"
    else:
        # A retained physical credential without a safe person link may prove
        # credential presence only when exactly one distinct credential exists.
        if len(credentials) != 1:
            reason = "NO_IDENTITY_LINEAGE" if not credentials else "AMBIGUOUS_CREDENTIAL"
            return dict(state="UNKNOWN", person_id=None,
                        reader_id=next(iter(reader_ids)) if len(reader_ids) == 1 else None,
                        credential_id=None, resolution_code="UNRESOLVED", unresolved_reason=reason, movement_at=None)
        credential = next(iter(credentials))
        if current_orphan_credential is None or not current_orphan_credential(credential):
            return dict(state="UNKNOWN", person_id=None,
                        reader_id=next(iter(reader_ids)) if len(reader_ids) == 1 else None,
                        credential_id=None, resolution_code="RETAINED_CREDENTIAL",
                        unresolved_reason="NO_CURRENT_CREDENTIAL", movement_at=None)
        resolution = "RETAINED_CREDENTIAL"

    current = movement(credential)
    if current is None:
        return dict(state="UNKNOWN", person_id=person_id,
                    reader_id=next(iter(reader_ids)) if len(reader_ids) == 1 else None,
                    credential_id=credential, resolution_code=resolution,
                    unresolved_reason="NO_AUTHORITATIVE_MOVEMENT", movement_at=None)
    stale = current["state"] == "UNKNOWN"
    return dict(state=current["state"], person_id=person_id,
                reader_id=next(iter(reader_ids)) if len(reader_ids) == 1 and not ambiguous_reader else None,
                credential_id=credential, resolution_code=resolution,
                unresolved_reason="STALE_AUTHORITATIVE_MOVEMENT" if stale else None,
                movement_at=current["at"], suppress_reader_projection=ambiguous_reader)


def reconcile_factory_presence(
    db: Session,
    config: FactoryPerimeterSettings,
    *,
    source: tuple[Callable, Callable, Callable] | None = None,
    verified_at: datetime | None = None,
) -> int:
    """Update the current-state projection; never creates movement-history rows."""
    if not config.enabled or config.badge_source != "EXTERNAL":
        return 0
    verified_at = verified_at or datetime.now(timezone.utc)
    candidates = _collect_candidates(db, config.factory_code)
    connection = None
    try:
        if source is None:
            connection = _connect()
            cursor = connection.cursor()
            try:
                rows = cursor.execute(_PRESENCE_CURRENT_IDENTITIES_SQL).fetchall()
            except Exception as exc:
                raise PresenceSourceError(_safe_odbc_category(exc, phase="query")) from None
            identities = []
            for row in rows:
                representation = _safe_text(row[0])
                # This result orders attr_value4 first for SQL Server lookup,
                # while PersonIdentity expects source person id first.
                source_id, person_pin, source_card_id, credential, card_pin = (
                    _safe_text(value) for value in row[1:6]
                )
                if not all((source_id, person_pin, source_card_id, credential, card_pin)) or person_pin != card_pin:
                    continue
                identity = PersonIdentity(source_id, person_pin, source_card_id, credential)
                reader_id = None
                if representation:
                    try:
                        reader_id = _attr_value_to_reader_number(representation)
                    except ValueError:
                        pass
                identities.append(PersonIdentity(
                    identity.source_person_id, identity.person_id,
                    identity.source_card_id, identity.credential_id, reader_id,
                ))
            source = _source_resolver_from_snapshot(cursor, identities, candidates_credentials := {
                credential for item in candidates.values() for credential in item.credential_ids
            })
        by_reader, current_credentials, movement = source[:3]
        if len(source) > 3:
            movement.current_orphan_credential = source[3]
        existing = {row.tracking_key: row for row in db.scalars(select(FactoryPresenceProjection).where(
            FactoryPresenceProjection.factory_code == config.factory_code
        )).all()}
        changed = 0
        for key, candidate in candidates.items():
            try:
                expected = _expected_for_candidate(candidate, by_reader, current_credentials, movement)
            except PresenceSourceError as exc:
                expected = dict(state="UNKNOWN", person_id=candidate.person_id,
                                reader_id=next(iter(candidate.reader_ids)) if len(candidate.reader_ids) == 1 else None,
                                credential_id=None, resolution_code="SOURCE_UNAVAILABLE",
                                unresolved_reason=exc.category, movement_at=None)
            except Exception:
                logger.exception("Factory presence identity resolution failed factory=%s", config.factory_code)
                expected = dict(state="UNKNOWN", person_id=candidate.person_id,
                                reader_id=next(iter(candidate.reader_ids)) if len(candidate.reader_ids) == 1 else None,
                                credential_id=None, resolution_code="UNRESOLVED",
                                unresolved_reason="QUERY_FAILED", movement_at=None)
            if expected["person_id"]:
                primary_key = f"PERSON:{expected['person_id']}"
                tracking_keys = [primary_key]
                if not expected.get("suppress_reader_projection"):
                    tracking_keys.extend(f"READER:{reader}" for reader in sorted(candidate.reader_ids))
            elif expected["reader_id"]:
                tracking_keys = [f"READER:{expected['reader_id']}"]
            elif expected["credential_id"] and expected["resolution_code"] == "RETAINED_CREDENTIAL":
                tracking_keys = [f"CREDENTIAL:{expected['credential_id']}" ,
                                 *(f"READER:{reader}" for reader in sorted(candidate.reader_ids))]
            else:
                tracking_keys = [key]
            secondary = {item["tracking_key"]: item for item in expected.get("secondary_projections", [])}
            tracking_keys.extend(key for key in secondary if key not in tracking_keys)
            values = {
                "person_id": expected["person_id"],
                "reader_id": expected["reader_id"],
                "credential_id": expected["credential_id"],
                "state": expected["state"],
                "source_system": SOURCE,
                "resolution_code": expected["resolution_code"],
                "source_movement_at": expected["movement_at"],
                "unresolved_reason": expected["unresolved_reason"],
            }
            for tracking_key in tracking_keys:
                row_values = dict(values)
                if tracking_key in secondary:
                    item = secondary[tracking_key]
                    row_values.update(
                        person_id=None,
                        reader_id=item["reader_id"],
                        credential_id=item["credential_id"],
                        state=item["state"],
                        resolution_code=item["resolution_code"],
                        unresolved_reason=item["unresolved_reason"],
                        source_movement_at=item["movement_at"],
                    )
                row = existing.get(tracking_key)
                if expected["person_id"] and row is None and tracking_key == primary_key:
                    row = existing.get(key)
                    if row is not None:
                        row.tracking_key = tracking_key
                        existing.pop(key, None)
                        existing[tracking_key] = row
                if row is not None and all(_same_value(getattr(row, name), value) for name, value in row_values.items()):
                    continue
                if tracking_key.startswith("READER:"):
                    row_values["reader_id"] = tracking_key.removeprefix("READER:")
                if row is None:
                    row = FactoryPresenceProjection(factory_code=config.factory_code, tracking_key=tracking_key, **row_values)
                    db.add(row)
                    existing[tracking_key] = row
                else:
                    for name, value in row_values.items():
                        setattr(row, name, value)
                row.verified_at = verified_at
                changed += 1
        db.commit()
        return changed
    except Exception as exc:
        # If the connection itself fails, every previously inferred current
        # state loses current authoritative support and must be UNKNOWN.
        logger.exception("Factory presence reconciliation failed factory=%s", config.factory_code)
        category = exc.category if isinstance(exc, PresenceSourceError) else "QUERY_FAILED"
        now = verified_at
        changed = 0
        rows = db.scalars(select(FactoryPresenceProjection).where(
            FactoryPresenceProjection.factory_code == config.factory_code
        )).all()
        for row in rows:
            if row.state != "UNKNOWN" or row.unresolved_reason != category or row.resolution_code != "SOURCE_UNAVAILABLE":
                row.state = "UNKNOWN"
                row.unresolved_reason = category
                row.resolution_code = "SOURCE_UNAVAILABLE"
                row.credential_id = None
                row.source_movement_at = None
                row.verified_at = now
                changed += 1
        for key, candidate in candidates.items():
            tracking_key = f"PERSON:{candidate.person_id}" if candidate.person_id else key
            if any(row.tracking_key == tracking_key for row in rows):
                continue
            db.add(FactoryPresenceProjection(
                factory_code=config.factory_code, tracking_key=tracking_key,
                person_id=candidate.person_id,
                reader_id=next(iter(candidate.reader_ids)) if len(candidate.reader_ids) == 1 else None,
                credential_id=None, state="UNKNOWN", source_system=SOURCE,
                resolution_code="SOURCE_UNAVAILABLE", unresolved_reason=category,
                source_movement_at=None, verified_at=now,
            ))
            changed += 1
        db.commit()
        return changed
    finally:
        if connection is not None:
            connection.close()


def reconcile_enabled_factory_presence() -> int:
    from app.db.session import SessionLocal

    total = 0
    with SessionLocal() as db:
        configs = db.scalars(select(FactoryPerimeterSettings).where(
            FactoryPerimeterSettings.enabled.is_(True), FactoryPerimeterSettings.badge_source == "EXTERNAL"
        )).all()
        for config in configs:
            try:
                total += reconcile_factory_presence(db, config)
            except PresenceSourceError as exc:
                db.rollback()
                logger.warning("Factory presence projection failed factory=%s category=%s", config.factory_code, exc.category)
            except Exception:
                db.rollback()
                logger.exception("Factory presence projection failed factory=%s", config.factory_code)
    return total


def reconcile_factory_presence_twice(db: Session, config: FactoryPerimeterSettings, *, source=None):
    """Run two consecutive passes and return their independent change counts."""
    first = reconcile_factory_presence(db, config, source=source)
    second = reconcile_factory_presence(db, config, source=source)
    return first, second
