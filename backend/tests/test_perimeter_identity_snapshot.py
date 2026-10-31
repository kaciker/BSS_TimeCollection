from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - register mapped tables
from app.db.base import Base
from app.models.perimeter import FactoryPerimeterEvent, FactoryPerimeterSettings
from app.models.person_badge_assignment import PersonBadgeAssignment
from app.models.factory import Factory
from app.services.external_perimeter_sync import ensure_virtual_terminal, mirror_external_event


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Factory(code="ARGANDA", name="Arganda"))
        session.commit()
        yield session
    engine.dispose()


def _assignment(reader_id: str, *, suffix: str = "1") -> PersonBadgeAssignment:
    observed = datetime(2026, 10, 28, 14, 0, tzinfo=timezone.utc)
    return PersonBadgeAssignment(
        factory_code="ARGANDA",
        source_system="SQLSERVER_SECURITY_DB",
        source_person_id=f"PERSON-{suffix}",
        person_id=f"27{suffix}",
        source_card_id=f"CARD-PK-{suffix}",
        credential_id=f"CARD-{suffix}",
        reader_id=reader_id,
        observed_from=observed,
        observed_to=None,
        first_seen_at=observed,
        last_seen_at=observed,
    )


def _config() -> FactoryPerimeterSettings:
    return FactoryPerimeterSettings(
        factory_code="ARGANDA",
        enabled=True,
        badge_source="EXTERNAL",
        dedup_enabled=True,
        dedup_seconds=5,
    )


def test_mirror_external_event_freezes_active_identity_before_insert(db):
    reader_id = "3226291488"
    config = _config()
    db.add_all([config, _assignment(reader_id)])
    db.commit()
    terminal = ensure_virtual_terminal(db, "ARGANDA")

    assert mirror_external_event(
        db,
        config,
        terminal,
        {
            "log_id": 12345,
            "event_time": datetime(2026, 10, 28, 15, 20, 2, tzinfo=timezone.utc),
            "zone_code": 2,
            "reporter_id": reader_id,
        },
    ) is True
    db.commit()

    event = db.scalar(select(FactoryPerimeterEvent))
    assert event is not None
    assert event.reporter_id == reader_id
    assert event.source_person_id == "PERSON-1"
    assert event.person_id == "271"
    assert event.credential_id == "CARD-1"


def test_mirror_external_event_fails_closed_for_ambiguous_active_identity(db):
    reader_id = "3226291488"
    config = _config()
    db.add_all([config, _assignment(reader_id, suffix="1"), _assignment(reader_id, suffix="2")])
    db.commit()
    terminal = ensure_virtual_terminal(db, "ARGANDA")

    assert mirror_external_event(
        db,
        config,
        terminal,
        {
            "log_id": 12346,
            "event_time": datetime(2026, 10, 28, 15, 21, 2, tzinfo=timezone.utc),
            "zone_code": 2,
            "reporter_id": reader_id,
        },
    ) is True
    db.commit()

    event = db.scalar(select(FactoryPerimeterEvent))
    assert event is not None
    assert event.source_person_id is None
    assert event.person_id is None
    assert event.credential_id is None
