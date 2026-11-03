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
        query=lambda *candidates: seen.append(candidates) or [
            (candidates[0], "PERSON-PK-1", "104582", "CARD-PK-1", "CARD-A", "104582")
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
        query=lambda *candidates: [
            (candidates[-1], "PERSON-PK-1", "104582", "CARD-PK-1", "CARD-A", "104582")
        ],
    )
    assert identity.reader_id == "2959281396"


def test_resolve_person_identity_accepts_same_identity_from_both_representations():
    identity = resolve_person_identity(
        "1012148397",
        query=lambda *candidates: [
            (candidates[0], "PERSON-PK-1", "104582", "CARD-PK-1", "CARD-A", "104582"),
            (candidates[-1], "PERSON-PK-1", "104582", "CARD-PK-1", "CARD-A", "104582"),
        ],
    )
    assert identity.person_id == "104582"


def test_resolve_person_identity_rejects_raw_swapped_collision():
    with pytest.raises(PersonIdentityError, match="AMBIGUOUS_IDENTITY"):
        resolve_person_identity(
            "1012148397",
            query=lambda *candidates: [
                (candidates[0], "PERSON-PK-1", "104582", "CARD-PK-1", "CARD-A", "104582"),
                (candidates[-1], "PERSON-PK-2", "104583", "CARD-PK-2", "CARD-B", "104583"),
            ],
        )


def test_resolve_person_identity_rejects_multiple_identities_for_one_representation():
    with pytest.raises(PersonIdentityError, match="AMBIGUOUS_IDENTITY"):
        resolve_person_identity(
            "1012148397",
            query=lambda *candidates: [
                (candidates[0], "PERSON-PK-1", "104582", "CARD-PK-1", "CARD-A", "104582"),
                (candidates[0], "PERSON-PK-2", "104583", "CARD-PK-2", "CARD-B", "104583"),
            ],
        )


def test_resolve_person_identity_fails_closed_when_matching_sql_row_is_invalid():
    with pytest.raises(PersonIdentityError, match="AMBIGUOUS_IDENTITY"):
        resolve_person_identity(
            "1012148397",
            query=lambda *candidates: [
                (candidates[0], "PERSON-PK-1", "104582", "CARD-PK-1", "CARD-A", "not-person-pin"),
                (candidates[0], "PERSON-PK-2", "104583", "CARD-PK-2", "CARD-B", "104583"),
            ],
        )


def test_resolve_person_identity_returns_not_found_when_neither_representation_matches():
    with pytest.raises(PersonIdentityError, match="IDENTITY_NOT_FOUND"):
        resolve_person_identity(
            "1012148397",
            query=lambda *_: [],
        )


@pytest.mark.parametrize("reader_id", ["", "abc", "4294967296", "-1", "１２３"])
def test_resolve_person_identity_rejects_invalid_reader_id(reader_id):
    with pytest.raises(PersonIdentityError, match="INVALID_READER_ID"):
        resolve_person_identity(reader_id, query=lambda *_: [])


def test_resolve_person_identity_preserves_leading_zero_raw_candidate():
    seen = []
    resolve_person_identity(
        "0582609699",
        query=lambda *candidates: seen.extend(candidates) or [
            (candidates[0], "PERSON-PK-1", "104582", "CARD-PK-1", "CARD-A", "104582")
        ],
    )
    assert "0582609699" in seen
    assert "582609699" in seen


def test_reader_candidates_include_exact_numeric_raw_and_swapped():
    from app.services.rfid_identity import rfid_candidates

    assert rfid_candidates("0542128736") == ("0542128736", "542128736", "1614434336")


@pytest.mark.parametrize("invalid_reader", [" 0542128736", "0542128736 ", "０542128736"])
def test_reader_candidate_input_requires_unpadded_ascii_decimal_string(invalid_reader):
    from app.services.rfid_identity import rfid_candidates

    with pytest.raises(ValueError):
        rfid_candidates(invalid_reader)


@pytest.mark.parametrize("representation", ["542128736", "1614434336", "0542128736"])
def test_zero_padded_reader_resolves_each_security_representation(representation):
    from app.services.rfid_identity import rfid_candidates

    candidates = rfid_candidates("0542128736")
    identity = resolve_person_identity(
        "0542128736",
        query=lambda *_: [(representation, "P-1501", "1501", "CARD-ROW", "CARD-1501", "1501")],
    )
    assert identity.person_id == "1501"
    assert identity.credential_id == "CARD-1501"
    assert identity.reader_id == "0542128736"
    assert representation in candidates


def test_equivalent_raw_representations_for_same_identity_resolve():
    identity = resolve_person_identity(
        "0542128736",
        query=lambda *_: [
            ("0542128736", "P-1501", "1501", "CARD-ROW", "CARD-1501", "1501"),
            ("542128736", "P-1501", "1501", "CARD-ROW", "CARD-1501", "1501"),
        ],
    )
    assert identity.person_id == "1501"


def test_zero_padded_reader_raw_swapped_collision_fails_closed():
    with pytest.raises(PersonIdentityError, match="AMBIGUOUS_IDENTITY"):
        resolve_person_identity(
            "0542128736",
            query=lambda *_: [
                ("542128736", "P-1501", "1501", "CARD-ROW", "CARD-1501", "1501"),
                ("1614434336", "P-1502", "1502", "CARD-ROW2", "CARD-1502", "1502"),
            ],
        )


def test_query_adapter_receives_only_candidates_as_separate_parameters():
    seen = []
    resolve_person_identity("0542128736", query=lambda *values: seen.extend(values) or [
        ("542128736", "P-1501", "1501", "CARD-ROW", "CARD-1501", "1501")
    ])
    assert "0542128736" in seen
    assert "542128736" in seen
    assert "1614434336" in seen


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


def test_current_snapshot_keeps_one_active_assignment_for_equivalent_reader_forms(db):
    first = datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc)
    identities = [
        PersonIdentity("P-1501", "1501", "CARD-ROW", "CARD-1501", "0542128736"),
        PersonIdentity("P-1501", "1501", "CARD-ROW", "CARD-1501", "542128736"),
        PersonIdentity("P-1501", "1501", "CARD-ROW", "CARD-1501", "1614434336"),
    ]
    assert apply_current_snapshot(db, "ARGANDA", identities, observed_at=first) == 1
    db.commit()
    rows = db.scalars(select(PersonBadgeAssignment).where(PersonBadgeAssignment.observed_to.is_(None))).all()
    assert len(rows) == 1


def test_current_snapshot_rejects_canonical_reader_collision_between_people(db):
    identities = [
        PersonIdentity("P-1501", "1501", "CARD-ROW-1", "CARD-1501", "0542128736"),
        PersonIdentity("P-1502", "1502", "CARD-ROW-2", "CARD-1502", "1614434336"),
    ]
    with pytest.raises(PersonIdentityError, match="AMBIGUOUS_CURRENT_MAPPING"):
        apply_current_snapshot(db, "ARGANDA", identities)
    assert db.scalars(select(PersonBadgeAssignment)).all() == []
