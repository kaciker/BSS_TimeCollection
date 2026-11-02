from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa
from app.db.base import Base
from app.models.factory import Factory
from app.models.action import Action
from app.models.perimeter import FactoryPerimeterEvent, FactoryPerimeterSettings, FactoryPresenceProjection
from app.models.person_badge_assignment import PersonBadgeAssignment
from app.models.terminal import Terminal
from app.models.time_event import TimeEvent
from app.models.action import Action
from app.services.factory_presence import reconcile_factory_presence
from app.services.person_identity import PersonIdentity, PersonIdentityError


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Factory(code="ARGANDA", name="Arganda"))
        db.flush()
        db.add_all([
            Action(id=1, code="START", label="Start", supplier_device_event="START", state_effect="ENTER", oracle_attributes={}, active=True),
            FactoryPerimeterSettings(factory_code="ARGANDA", enabled=True, badge_source="EXTERNAL"),
            Terminal(factory_code="ARGANDA", terminal_role="CELL", code="CELL", name="Cell", external_device_id="CELL", identification_mode="BOTH", reporter_id_type="BADGE", oracle_attributes={}, active=True),
            Terminal(factory_code="ARGANDA", terminal_role="PERIMETER_BOTH", code="GATE", name="Gate", external_device_id="GATE", identification_mode="RFID", reporter_id_type="BADGE", oracle_attributes={}, active=True),
        ])
        db.commit()
        yield db
    engine.dispose()


def identity(person="3627", credential="CARD-3627", source="SEC-3627"):
    return PersonIdentity(source, person, "CARDROW-" + credential, credential, None)


def source_for(*, cards=None, moves=None, readers=None):
    cards = cards or {}
    moves = moves or {}
    readers = readers or {}

    def by_reader(reader):
        result = readers.get(reader)
        if isinstance(result, Exception):
            raise result
        if result is None:
            raise PersonIdentityError("IDENTITY_NOT_FOUND")
        return result

    return by_reader, lambda person: list(cards.get(person, [])), lambda credential: moves.get(credential)


def keypad_event(db, *, person="3627", reporter="3627", at=None):
    at = at or datetime(2026, 11, 2, 8, tzinfo=timezone.utc)
    terminal = db.scalar(select(Terminal).where(Terminal.code == "CELL"))
    db.add(TimeEvent(
        id="event-" + person, request_number="request-" + person, terminal_id=terminal.id,
        action_id=1, terminal_code="CELL", device_id="CELL", action_code="ENTER", action_label="Enter",
        supplier_device_event="ENTER", state_effect="ENTER", reporter_id=reporter,
        reporter_id_type="PERSON", identification_method="KEYPAD", event_datetime=at,
        event_timezone="UTC", oracle_attributes={}, delivery_status="PENDING", created_at=at,
        person_id=person, source_person_id="SEC-" + person, oracle_reporter_id=person,
        oracle_reporter_id_type="PERSON",
    ))
    db.commit()


def test_keypad_person_uses_current_unique_physical_credential_and_is_idempotent(session):
    keypad_event(session)
    before = session.scalar(select(func.count()).select_from(FactoryPerimeterEvent))
    source = source_for(cards={"3627": [identity()]}, moves={"CARD-3627": {"state": "INSIDE", "at": datetime(2026, 11, 2, 7, tzinfo=timezone.utc)}})
    assert reconcile_factory_presence(session, session.get(FactoryPerimeterSettings, "ARGANDA"), source=source) == 1
    row = session.scalar(select(FactoryPresenceProjection))
    assert (row.person_id, row.credential_id, row.state, row.resolution_code) == ("3627", "CARD-3627", "INSIDE", "CANONICAL_PERSON_CURRENT_CREDENTIAL")
    assert row.reader_id is None
    assert reconcile_factory_presence(session, session.get(FactoryPerimeterSettings, "ARGANDA"), source=source) == 0
    assert session.scalar(select(func.count()).select_from(FactoryPerimeterEvent)) == before


def test_rfid_resolves_person_then_reads_movement_by_physical_credential(session):
    at = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
    session.add(PersonBadgeAssignment(factory_code="ARGANDA", source_system="SQLSERVER_SECURITY_DB",
        source_person_id="SEC-3627", person_id="3627", source_card_id="CARDROW-CARD-3627",
        credential_id="CARD-3627", reader_id="0537312724", observed_from=at,
        first_seen_at=at, last_seen_at=at))
    session.commit()
    calls = []
    source = source_for(readers={"0537312724": identity()}, cards={"3627": [identity()]},
        moves={"CARD-3627": {"state": "OUTSIDE", "at": at}})
    by_reader, cards, move = source
    wrapped = (by_reader, cards, lambda credential: (calls.append(credential) or move(credential)))
    reconcile_factory_presence(session, session.get(FactoryPerimeterSettings, "ARGANDA"), source=wrapped)
    row = session.scalar(select(FactoryPresenceProjection))
    assert row.person_id == "3627" and row.reader_id == "0537312724" and row.state == "OUTSIDE"
    assert calls == ["CARD-3627"]


def test_reader_with_multiple_card_rows_uses_unique_person_and_unique_current_card():
    from app.services.factory_presence import _source_resolver

    class Cursor:
        def execute(self, sql, *_params):
            self.sql = sql
            return self
        def fetchall(self):
            if "TRY_CONVERT" in self.sql or "WHERE p.pin" in self.sql:
                return []
            if "WHERE p.pin = ?" in self.sql:
                return []
            if "WHERE pc.card_no" in self.sql:
                return []
            if "pc.card_state" in self.sql:
                return []
            return [
                ("0537312724", "SEC-3627", "3627", "OLD-CARD-ROW", "OLD-CARD", "3627"),
                ("0537312724", "SEC-3627", "3627", "CURRENT-CARD-ROW", "CURRENT-CARD", "3627"),
            ]

    by_reader, current_cards, _movement, _orphan = _source_resolver(Cursor())
    # Multiple card joins do not create multiple employee identities.
    assert by_reader("0537312724").person_id == "3627"
    assert current_cards("3627") == []  # no current credential means caller returns UNKNOWN


def test_historical_reader_resolves_person_then_uses_replacement_current_card(session):
    at = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
    session.add(PersonBadgeAssignment(factory_code="ARGANDA", source_system="SQLSERVER_SECURITY_DB",
        source_person_id="SEC-3627", person_id="3627", source_card_id="OLD-ROW",
        credential_id="OLD-CARD", reader_id="0537312724", observed_from=at,
        first_seen_at=at, last_seen_at=at, observed_to=at))
    session.add(FactoryPerimeterEvent(id="old-reader", factory_code="ARGANDA", reporter_id="0537312724",
        terminal_id=session.scalar(select(Terminal).where(Terminal.code == "GATE")).id,
        direction="ENTER", event_datetime=at, correlation_id="old-reader", credential_id="OLD-CARD"))
    session.commit()
    looked_up = []
    source = source_for(cards={"3627": [identity(credential="NEW-CARD")]},
        moves={"NEW-CARD": {"state": "OUTSIDE", "at": at}})
    by_reader, current_cards, movement = source
    def no_historical_resolution(_reader):
        raise PersonIdentityError("IDENTITY_NOT_FOUND")
    reconcile_factory_presence(session, session.get(FactoryPerimeterSettings, "ARGANDA"),
        source=(no_historical_resolution, current_cards,
                lambda credential: (looked_up.append(credential) or movement(credential))))
    rows = session.scalars(select(FactoryPresenceProjection)).all()
    assert any(row.person_id == "3627" and row.credential_id == "NEW-CARD"
               and row.state == "OUTSIDE"
               and row.resolution_code == "HISTORICAL_PERSON_CURRENT_CREDENTIAL" for row in rows)
    assert looked_up == ["NEW-CARD"]


def test_strict_decimal_normalization_resolves_unique_representation_and_rejects_collision():
    from app.services.factory_presence import _source_resolver

    class Cursor:
        rows = []
        def execute(self, sql, *params):
            self.sql, self.params = sql, params
            return self
        def fetchall(self):
            return self.rows

    cursor = Cursor()
    by_reader, _, _, _ = _source_resolver(cursor)
    cursor.rows = []
    # The validated raw/swapped resolver returns no exact textual hit; strict
    # decimal normalization then accepts one equivalent spelling.
    def execute_and_fill(sql, *params):
        cursor.sql, cursor.params = sql, params
        cursor.rows = [] if "TRY_CONVERT" not in sql else [
            ("00537312724", "SEC-3627", "3627", "CARDROW", "CARD-3627", "3627")
        ]
        return cursor
    cursor.execute = execute_and_fill
    resolved = by_reader("0537312724")
    assert resolved.person_id == "3627"

    def collision(sql, *params):
        cursor.rows = [] if "TRY_CONVERT" not in sql else [
            ("00537312724", "SEC-A", "3627", "CARD-A", "CARD-A", "3627"),
            ("537312724", "SEC-B", "3634", "CARD-B", "CARD-B", "3634"),
        ]
        return cursor
    cursor.execute = collision
    by_reader, _, _, _ = _source_resolver(cursor)
    with pytest.raises(PersonIdentityError, match="AMBIGUOUS_IDENTITY"):
        by_reader("0537312724")


def test_ambiguous_current_credentials_fail_closed(session):
    keypad_event(session)
    source = source_for(cards={"3627": [identity(credential="CARD-A"), identity(credential="CARD-B")]},
        moves={"CARD-A": {"state": "INSIDE"}, "CARD-B": {"state": "OUTSIDE"}})
    reconcile_factory_presence(session, session.get(FactoryPerimeterSettings, "ARGANDA"), source=source)
    row = session.scalar(select(FactoryPresenceProjection))
    assert row.state == "UNKNOWN" and row.unresolved_reason == "AMBIGUOUS_CURRENT_CREDENTIAL"
    assert row.credential_id is None


def test_identity_loss_moves_old_inside_to_unknown_and_recovery_updates_state(session):
    keypad_event(session)
    config = session.get(FactoryPerimeterSettings, "ARGANDA")
    good = source_for(cards={"3627": [identity()]}, moves={"CARD-3627": {"state": "INSIDE", "at": datetime(2026, 11, 2, 7, tzinfo=timezone.utc)}})
    reconcile_factory_presence(session, config, source=good)
    no_card = source_for(cards={"3627": []})
    assert reconcile_factory_presence(session, config, source=no_card) == 1
    row = session.scalar(select(FactoryPresenceProjection))
    assert row.state == "UNKNOWN" and row.unresolved_reason == "NO_CURRENT_CREDENTIAL"
    recovered = source_for(cards={"3627": [identity()]}, moves={"CARD-3627": {"state": "OUTSIDE", "at": datetime(2026, 11, 2, 10, tzinfo=timezone.utc)}})
    assert reconcile_factory_presence(session, config, source=recovered) == 1
    assert row.state == "OUTSIDE" and row.unresolved_reason is None


def test_missing_movement_and_unlinked_identity_are_unknown(session):
    keypad_event(session)
    config = session.get(FactoryPerimeterSettings, "ARGANDA")
    reconcile_factory_presence(session, config, source=source_for(cards={"3627": [identity()]}))
    row = session.scalar(select(FactoryPresenceProjection))
    assert row.state == "UNKNOWN" and row.unresolved_reason == "NO_AUTHORITATIVE_MOVEMENT"


def test_orphan_credential_uses_authoritative_state_only_when_still_current(session):
    terminal = session.scalar(select(Terminal).where(Terminal.code == "GATE"))
    at = datetime(2026, 11, 2, 8, tzinfo=timezone.utc)
    session.add(FactoryPerimeterEvent(id="orphan-event", factory_code="ARGANDA", reporter_id="777",
        credential_id="ORPHAN-CARD", terminal_id=terminal.id, direction="ENTER", event_datetime=at,
        correlation_id="orphan"))
    session.commit()
    source = source_for(moves={"ORPHAN-CARD": {"state": "INSIDE", "at": at}})
    source = (*source, lambda credential: credential == "ORPHAN-CARD")
    reconcile_factory_presence(session, session.get(FactoryPerimeterSettings, "ARGANDA"), source=source)
    row = session.scalar(select(FactoryPresenceProjection))
    assert row.state == "INSIDE" and row.person_id is None
    assert row.resolution_code == "RETAINED_CREDENTIAL"


def test_unknown_person_is_materialized_and_monitoring_filters_use_projection(session):
    from fastapi.testclient import TestClient
    from app.db.session import get_db
    from app.main import app
    from app.models.action import Action
    from app.models.factory import InstallationSettings

    terminal = session.scalar(select(Terminal).where(Terminal.code == "CELL"))
    at = datetime(2026, 11, 2, 8, tzinfo=timezone.utc)
    session.add(TimeEvent(id="unknown-event", request_number="unknown-request", terminal_id=terminal.id,
        action_id=1, terminal_code="CELL", device_id="CELL", action_code="START", action_label="Start",
        supplier_device_event="START", state_effect="ENTER", reporter_id="9999", reporter_id_type="PERSON",
        identification_method="KEYPAD", event_datetime=at, event_timezone="UTC", oracle_attributes={},
        delivery_status="PENDING", created_at=at, person_id="9999"))
    session.add(InstallationSettings(id=1, default_factory_code="ARGANDA"))
    session.commit()
    config = session.get(FactoryPerimeterSettings, "ARGANDA")
    unknown_source = source_for(cards={"9999": []})
    reconcile_factory_presence(session, config, source=unknown_source)
    overrides = {get_db: lambda: session}
    app.dependency_overrides.update(overrides)
    try:
        with TestClient(app) as client:
            all_rows = client.get("/api/v1/admin/monitoring/cards").json()
            assert all_rows["total"] == 1
            card = all_rows["items"][0]
            assert card["factory_state"] == "UNKNOWN"
            assert card["factory_reason"] == "NO_CURRENT_CREDENTIAL"
            assert client.get("/api/v1/admin/monitoring/cards?factory_state=UNKNOWN").json()["total"] == 1
            assert client.get("/api/v1/admin/monitoring/cards?factory_state=INSIDE").json()["total"] == 0
            assert client.get("/api/v1/admin/monitoring/cards?factory_state=OUTSIDE").json()["total"] == 0
    finally:
        app.dependency_overrides.clear()


def test_projection_is_separate_from_historical_movement(session):
    keypad_event(session)
    gate = session.scalar(select(Terminal).where(Terminal.code == "GATE"))
    at = datetime(2026, 11, 1, 8, tzinfo=timezone.utc)
    session.add(FactoryPerimeterEvent(id="history", factory_code="ARGANDA", reporter_id="0537312724",
        terminal_id=gate.id, direction="ENTER", event_datetime=at, correlation_id="history"))
    session.commit()
    before = [(e.id, e.direction, e.event_datetime) for e in session.scalars(select(FactoryPerimeterEvent))]
    reconcile_factory_presence(session, session.get(FactoryPerimeterSettings, "ARGANDA"),
        source=source_for(cards={"3627": []}))
    after = [(e.id, e.direction, e.event_datetime) for e in session.scalars(select(FactoryPerimeterEvent))]
    assert before == after


def test_old_authoritative_enter_is_unknown_but_old_exit_remains_outside(monkeypatch):
    from app.core.config import settings
    from app.services.factory_presence import _movement

    class Cursor:
        def __init__(self, row):
            self.row = row
        def execute(self, _sql, _credential):
            return self
        def fetchone(self):
            return self.row

    monkeypatch.setattr(settings, "perimeter_external_max_age_hours", 12)
    stale = datetime(2026, 10, 1, 8, tzinfo=timezone.utc)
    assert _movement(Cursor(("old-enter", stale, "2")), "CARD") ["state"] == "UNKNOWN"
    assert _movement(Cursor(("old-exit", stale, "1")), "CARD")["state"] == "OUTSIDE"
