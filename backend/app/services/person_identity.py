"""Read-only SECURITY_DB identity resolution and local assignment observations."""
from dataclasses import dataclass
from datetime import datetime, timezone
import logging

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.person_badge_assignment import PersonBadgeAssignment
from app.models.perimeter import FactoryPerimeterSettings
from app.services.external_perimeter import (
    ExternalPerimeterError,
    _connection_string,
    _credentials,
    _safe_odbc_category,
    reader_number_to_attr_value,
)

logger = logging.getLogger(__name__)
SOURCE = "SQLSERVER_SECURITY_DB"

_RESOLVE_SQL = """
SELECT pae.attr_value4, p.id, p.pin, pc.id, pc.card_no, pc.person_pin
FROM dbo.pers_attribute_ext AS pae
JOIN dbo.pers_person AS p ON p.id = pae.person_id
JOIN dbo.pers_card AS pc ON pc.person_id = p.id
WHERE pae.attr_value4 IN (?, ?)
ORDER BY pae.attr_value4, p.id, pc.id
"""

_CURRENT_SQL = """
SELECT p.id, p.pin, pc.id, pc.card_no, pc.person_pin, pae.attr_value4
FROM dbo.pers_card AS pc
JOIN dbo.pers_person AS p ON p.id = pc.person_id
LEFT JOIN dbo.pers_attribute_ext AS pae ON pae.person_id = p.id
ORDER BY p.id, pc.id, pae.attr_value4
"""


class PersonIdentityError(RuntimeError):
    def __init__(self, category: str):
        super().__init__(category)
        self.category = category


@dataclass(frozen=True)
class PersonIdentity:
    source_person_id: str
    person_id: str
    source_card_id: str
    credential_id: str
    reader_id: str | None = None


def _connect():
    try:
        import pyodbc
    except ImportError:
        raise PersonIdentityError("ODBC_DRIVER_UNAVAILABLE") from None
    try:
        config = _credentials()
    except ExternalPerimeterError as exc:
        raise PersonIdentityError(exc.category) from None
    try:
        return pyodbc.connect(_connection_string(config), timeout=3, autocommit=True)
    except ExternalPerimeterError as exc:
        raise PersonIdentityError(exc.category) from None
    except Exception as exc:
        raise PersonIdentityError(_safe_odbc_category(exc, phase="connect")) from None


def _attr_value_to_reader_number(value: str) -> str:
    digits = str(value).strip()
    if not digits or not digits.isascii() or not digits.isdecimal():
        raise ValueError("External badge attribute must contain ASCII decimal digits")
    number = int(digits)
    if number >= 2 ** 32:
        raise ValueError("External badge attribute exceeds the validated 32-bit format")
    reader_number = int.from_bytes(number.to_bytes(4, "big"), "little")
    return f"{reader_number:010d}"


def _normalize_row(row, *, reader_id: str | None = None) -> PersonIdentity | None:
    try:
        values = row[0], row[1], row[2], row[3], row[4]
    except (TypeError, IndexError):
        return None
    if any(value is None for value in values):
        return None
    source_person_id, person_id, source_card_id, credential_id, person_pin = (
        str(value).strip() for value in values
    )
    if not all((source_person_id, person_id, source_card_id, credential_id, person_pin)):
        return None
    if person_pin != person_id:
        return None
    return PersonIdentity(
        source_person_id=source_person_id,
        person_id=person_id,
        source_card_id=source_card_id,
        credential_id=credential_id,
        reader_id=reader_id.strip() if reader_id else None,
    )


def resolve_person_identity(reader_id: str, *, query=None) -> PersonIdentity:
    """Resolve either supported decimal representation, failing closed on collisions."""
    try:
        digits = str(reader_id).strip()
        if not digits or not digits.isascii() or not digits.isdecimal():
            raise ValueError
        number = int(digits)
        if number >= 2**32:
            raise ValueError
        # Keep the terminal's exact decimal spelling, including RFID leading zeros.
        raw_value = digits
        converted = reader_number_to_attr_value(digits)
    except ValueError:
        raise PersonIdentityError("INVALID_READER_ID") from None

    if query is not None:
        try:
            rows = list(query(raw_value, converted))
        except Exception:
            raise PersonIdentityError("QUERY_FAILED") from None
    else:
        connection = _connect()
        try:
            rows = connection.cursor().execute(_RESOLVE_SQL, raw_value, converted).fetchall()
        except Exception as exc:
            raise PersonIdentityError(_safe_odbc_category(exc, phase="query")) from None
        finally:
            connection.close()

    by_representation: dict[str, set[PersonIdentity]] = {}
    invalid_representation_match = False
    for candidate in {raw_value, converted}:
        by_representation.setdefault(candidate, set())
    for row in rows:
        try:
            representation = str(row[0]).strip()
        except (TypeError, IndexError):
            continue
        if representation not in by_representation:
            continue
        identity = _normalize_row(row[1:], reader_id=digits)
        if identity is not None:
            by_representation[representation].add(identity)
        else:
            invalid_representation_match = True

    if invalid_representation_match or any(len(matches) > 1 for matches in by_representation.values()):
        logger.warning("Ambiguous SECURITY_DB identity reader_id=%s", digits)
        raise PersonIdentityError("AMBIGUOUS_IDENTITY")

    identities = set().union(*by_representation.values())
    if not identities:
        raise PersonIdentityError("IDENTITY_NOT_FOUND")
    if len(identities) != 1:
        logger.warning("Conflicting SECURITY_DB representations reader_id=%s", digits)
        raise PersonIdentityError("AMBIGUOUS_IDENTITY")
    return next(iter(identities))


def fetch_current_person_badges(*, query=None) -> list[PersonIdentity]:
    """Return the authoritative current pers_card mapping; reject ambiguous snapshots."""
    if query is not None:
        try:
            rows = list(query())
        except Exception:
            raise PersonIdentityError("QUERY_FAILED") from None
    else:
        connection = _connect()
        try:
            rows = connection.cursor().execute(_CURRENT_SQL).fetchall()
        except Exception as exc:
            raise PersonIdentityError(_safe_odbc_category(exc, phase="query")) from None
        finally:
            connection.close()

    grouped: dict[tuple[str, str, str, str], set[str]] = {}
    for row in rows:
        identity = _normalize_row(row)
        if identity is None:
            raise PersonIdentityError("INVALID_CURRENT_MAPPING")
        key = (
            identity.source_person_id,
            identity.person_id,
            identity.source_card_id,
            identity.credential_id,
        )
        readers = grouped.setdefault(key, set())
        try:
            attr_value = row[5]
        except (TypeError, IndexError):
            attr_value = None
        if attr_value is not None:
            try:
                readers.add(_attr_value_to_reader_number(str(attr_value)))
            except ValueError:
                pass

    identities = [
        PersonIdentity(*key, reader_id=next(iter(readers)) if len(readers) == 1 else None)
        for key, readers in grouped.items()
    ]

    by_person: dict[str, PersonIdentity] = {}
    by_credential: dict[str, PersonIdentity] = {}
    for identity in identities:
        existing_person = by_person.get(identity.source_person_id)
        existing_credential = by_credential.get(identity.credential_id)
        if existing_person is not None and existing_person != identity:
            raise PersonIdentityError("AMBIGUOUS_CURRENT_MAPPING")
        if existing_credential is not None and existing_credential != identity:
            raise PersonIdentityError("AMBIGUOUS_CURRENT_MAPPING")
        by_person[identity.source_person_id] = identity
        by_credential[identity.credential_id] = identity
    return identities


def observe_identity(
    db: Session,
    factory_code: str,
    identity: PersonIdentity,
    *,
    observed_at: datetime | None = None,
) -> bool:
    """Record one observed mapping without claiming the rest of the source snapshot."""
    observed_at = observed_at or datetime.now(timezone.utc)
    active = db.scalars(
        select(PersonBadgeAssignment).where(
            PersonBadgeAssignment.factory_code == factory_code,
            PersonBadgeAssignment.observed_to.is_(None),
            or_(
                PersonBadgeAssignment.source_person_id == identity.source_person_id,
                PersonBadgeAssignment.credential_id == identity.credential_id,
                PersonBadgeAssignment.reader_id == identity.reader_id if identity.reader_id else False,
            ),
        )
    ).all()
    exact = None
    changed = False
    for row in active:
        same_base = (
            row.source_person_id == identity.source_person_id
            and row.person_id == identity.person_id
            and row.source_card_id == identity.source_card_id
            and row.credential_id == identity.credential_id
        )
        if same_base and (row.reader_id == identity.reader_id or not identity.reader_id):
            exact = row
        elif same_base and row.reader_id is None and identity.reader_id:
            row.reader_id = identity.reader_id
            exact = row
            changed = True
        else:
            row.observed_to = observed_at
            changed = True
    if exact is not None:
        exact.last_seen_at = observed_at
        return changed

    db.add(
        PersonBadgeAssignment(
            factory_code=factory_code,
            source_system=SOURCE,
            source_person_id=identity.source_person_id,
            person_id=identity.person_id,
            source_card_id=identity.source_card_id,
            credential_id=identity.credential_id,
            reader_id=identity.reader_id,
            observed_from=observed_at,
            observed_to=None,
            first_seen_at=observed_at,
            last_seen_at=observed_at,
        )
    )
    return True


def apply_current_snapshot(
    db: Session,
    factory_code: str,
    identities: list[PersonIdentity],
    *,
    observed_at: datetime | None = None,
) -> int:
    """Reconcile local observations with one complete authoritative current snapshot."""
    observed_at = observed_at or datetime.now(timezone.utc)
    incoming_by_person = {identity.source_person_id: identity for identity in identities}
    incoming_by_credential = {identity.credential_id: identity for identity in identities}
    if len(incoming_by_person) != len(identities) or len(incoming_by_credential) != len(identities):
        raise PersonIdentityError("AMBIGUOUS_CURRENT_MAPPING")

    active = db.scalars(
        select(PersonBadgeAssignment).where(
            PersonBadgeAssignment.factory_code == factory_code,
            PersonBadgeAssignment.observed_to.is_(None),
        )
    ).all()
    changes = 0
    active_base: dict[tuple[str, str, str, str], PersonBadgeAssignment] = {}
    for row in active:
        key = (row.source_person_id, row.person_id, row.source_card_id, row.credential_id)
        active_base[key] = row
        incoming = incoming_by_person.get(row.source_person_id)
        if incoming is None or (
            incoming.person_id,
            incoming.source_card_id,
            incoming.credential_id,
        ) != (row.person_id, row.source_card_id, row.credential_id):
            row.observed_to = observed_at
            changes += 1
            continue
        if row.reader_id is None and incoming.reader_id:
            row.reader_id = incoming.reader_id
            changes += 1
        elif row.reader_id and incoming.reader_id and row.reader_id != incoming.reader_id:
            row.observed_to = observed_at
            changes += 1

    for identity in identities:
        key = (
            identity.source_person_id,
            identity.person_id,
            identity.source_card_id,
            identity.credential_id,
        )
        existing = active_base.get(key)
        if existing is not None and existing.observed_to is None:
            continue
        db.add(
            PersonBadgeAssignment(
                factory_code=factory_code,
                source_system=SOURCE,
                source_person_id=identity.source_person_id,
                person_id=identity.person_id,
                source_card_id=identity.source_card_id,
                credential_id=identity.credential_id,
                reader_id=identity.reader_id,
                observed_from=observed_at,
                observed_to=None,
                first_seen_at=observed_at,
                last_seen_at=observed_at,
            )
        )
        changes += 1
    return changes


def sync_enabled_person_badges() -> int:
    """Snapshot current mappings for factories using the external SECURITY_DB source."""
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
                identities = fetch_current_person_badges()
                changes = apply_current_snapshot(db, config.factory_code, identities)
                db.commit()
                total += changes
            except PersonIdentityError as exc:
                db.rollback()
                logger.warning(
                    "Person/badge snapshot failed factory=%s category=%s",
                    config.factory_code,
                    exc.category,
                )
            except Exception:
                db.rollback()
                logger.exception(
                    "Unexpected person/badge snapshot failure factory=%s",
                    config.factory_code,
                )
    return total
