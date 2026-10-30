from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - register mapped tables
from app.db.base import Base
from app.models.person_badge_assignment import PersonBadgeAssignment
from app.services.person_identity import (
    PersonIdentity,
    PersonIdentityError,
    apply_current_snapshot,
    resolve_person_identity,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _utc(value):
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def test_resolve_person_identity_raw_only_mapping():
    seen = []
    identity = resolve_person_identity(
        "1012148397",
        query=lambda raw, swapped: seen.append((raw, swapped)) or [
            (raw, "PERSON-PK-1", "104582", "CARD-PK-1", "CARD-A", "104582")
        ],
    )
    assert seen == [("1012148397", "2905101372")]
    assert identity == PersonIdentity(
        source_person_id="PERSON-PK-1",
        person_id="104582",
        source_card_id="CARD-PK-1",
        credential_id="CARD-A",
        reader_id="1012148397",
    )


def test_resolve_person_identity_swapped_only_mapping():
    identity = resolve_person_identity(
        "2959281396",
        query=lambda raw, swapped: [
            (swapped, "PERSON-PK-1", "104582", "CARD-PK-1", "CARD-A", "104582")
        ],
    )
    assert identity.reader_id == "2959281396"


def test_resolve_person_identity_accepts_same_identity_from_both_representations():
    identity = resolve_person_identity(
        "1012148397",
        query=lambda raw, swapped: [
            (raw, "PERSON-PK-1", "104582", "CARD-PK-1", "CARD-A", "104582"),
            (swapped, "PERSON-PK-1", "104582", "CARD-PK-1", "CARD-A", "104582"),
        ],
    )
    assert identity.person_id == "104582"


def test_resolve_person_identity_rejects_raw_swapped_collision():
    with pytest.raises(PersonIdentityError, match="AMBIGUOUS_IDENTITY"):
        resolve_person_identity(
            "1012148397",
            query=lambda raw, swapped: [
                (raw, "PERSON-PK-1", "104582", "CARD-PK-1", "CARD-A", "104582"),
                (swapped, "PERSON-PK-2", "104583", "CARD-PK-2", "CARD-B", "104583"),
            ],
        )


def test_resolve_person_identity_rejects_multiple_identities_for_one_representation():
    with pytest.raises(PersonIdentityError, match="AMBIGUOUS_IDENTITY"):
        resolve_person_identity(
            "1012148397",
            query=lambda raw, swapped: [
                (raw, "PERSON-PK-1", "104582", "CARD-PK-1", "CARD-A", "104582"),
                (raw, "PERSON-PK-2", "104583", "CARD-PK-2", "CARD-B", "104583"),
            ],
        )


def test_resolve_person_identity_fails_closed_when_matching_sql_row_is_invalid():
    with pytest.raises(PersonIdentityError, match="AMBIGUOUS_IDENTITY"):
        resolve_person_identity(
            "1012148397",
            query=lambda raw, swapped: [
                (raw, "PERSON-PK-1", "104582", "CARD-PK-1", "CARD-A", "not-person-pin"),
                (raw, "PERSON-PK-2", "104583", "CARD-PK-2", "CARD-B", "104583"),
            ],
        )


def test_resolve_person_identity_returns_not_found_when_neither_representation_matches():
    with pytest.raises(PersonIdentityError, match="IDENTITY_NOT_FOUND"):
        resolve_person_identity(
            "1012148397",
            query=lambda raw, swapped: [],
        )


@pytest.mark.parametrize("reader_id", ["", "abc", "4294967296", "-1", "１２３"])
def test_resolve_person_identity_rejects_invalid_reader_id(reader_id):
    with pytest.raises(PersonIdentityError, match="INVALID_READER_ID"):
        resolve_person_identity(reader_id, query=lambda *_: [])


def test_resolve_person_identity_preserves_leading_zero_raw_candidate():
    seen = []
    resolve_person_identity(
        "0582609699",
        query=lambda raw, swapped: seen.append(raw) or [
            (raw, "PERSON-PK-1", "104582", "CARD-PK-1", "CARD-A", "104582")
        ],
    )
    assert seen == ["0582609699"]


def test_current_snapshot_closes_old_card_and_opens_new_assignment(db):
    first = datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc)
    second = first + timedelta(hours=2)
    old = PersonIdentity("PERSON-PK-1", "104582", "CARD-PK-1", "CARD-A", "0582609699")
    new = PersonIdentity("PERSON-PK-1", "104582", "CARD-PK-2", "CARD-B", "0582609700")

    assert apply_current_snapshot(db, "ARGANDA", [old], observed_at=first) == 1
    db.commit()
    assert apply_current_snapshot(db, "ARGANDA", [new], observed_at=second) == 2
    db.commit()

    rows = db.scalars(
        select(PersonBadgeAssignment).order_by(PersonBadgeAssignment.observed_from)
    ).all()
    assert len(rows) == 2
    assert rows[0].credential_id == "CARD-A"
    assert rows[0].reader_id == "0582609699"
    assert _utc(rows[0].observed_to) == second
    assert rows[1].credential_id == "CARD-B"
    assert rows[1].reader_id == "0582609700"
    assert _utc(rows[1].observed_from) == second
    assert rows[1].observed_to is None
