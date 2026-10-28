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


def test_resolve_person_identity_uses_pin_and_current_card():
    seen = []
    identity = resolve_person_identity(
        "0582609699",
        query=lambda converted: seen.append(converted) or [
            ("PERSON-PK-1", "104582", "CARD-PK-1", "CARD-A", "104582")
        ],
    )
    assert seen == ["602650914"]
    assert identity == PersonIdentity(
        source_person_id="PERSON-PK-1",
        person_id="104582",
        source_card_id="CARD-PK-1",
        credential_id="CARD-A",
    )


def test_resolve_person_identity_rejects_ambiguous_or_inconsistent_rows():
    with pytest.raises(PersonIdentityError, match="AMBIGUOUS_IDENTITY"):
        resolve_person_identity(
            "0582609699",
            query=lambda _: [
                ("PERSON-PK-1", "104582", "CARD-PK-1", "CARD-A", "104582"),
                ("PERSON-PK-2", "104583", "CARD-PK-2", "CARD-B", "104583"),
            ],
        )
    with pytest.raises(PersonIdentityError, match="IDENTITY_NOT_FOUND"):
        resolve_person_identity(
            "0582609699",
            query=lambda _: [("PERSON-PK-1", "104582", "CARD-PK-1", "CARD-A", "DIFFERENT")],
        )


def test_current_snapshot_closes_old_card_and_opens_new_assignment(db):
    first = datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc)
    second = first + timedelta(hours=2)
    old = PersonIdentity("PERSON-PK-1", "104582", "CARD-PK-1", "CARD-A")
    new = PersonIdentity("PERSON-PK-1", "104582", "CARD-PK-2", "CARD-B")

    assert apply_current_snapshot(db, "ARGANDA", [old], observed_at=first) == 1
    db.commit()
    assert apply_current_snapshot(db, "ARGANDA", [new], observed_at=second) == 2
    db.commit()

    rows = db.scalars(
        select(PersonBadgeAssignment).order_by(PersonBadgeAssignment.observed_from)
    ).all()
    assert len(rows) == 2
    assert rows[0].credential_id == "CARD-A"
    assert _utc(rows[0].observed_to) == second
    assert rows[1].credential_id == "CARD-B"
    assert _utc(rows[1].observed_from) == second
    assert rows[1].observed_to is None
