from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - register all mapped tables for SQLite tests
from app.core.config import settings
from app.db.base import Base
from app.models.action import Action
from app.models.perimeter import FactoryPerimeterEvent, FactoryPerimeterSettings
from app.models.terminal import Terminal
from app.models.time_event import TimeEvent
from app.models.transmission_attempt import TransmissionAttempt
from app.services.external_perimeter import reader_number_to_attr_value
from app.services.external_perimeter_sync import (
    attr_value_to_reader_number,
    ensure_virtual_terminal,
    external_events_after,
    external_inside_snapshot,
    mirror_external_event,
    reconcile_external_factory,
    sync_external_factory,
)

LOCAL_TZ = ZoneInfo(settings.event_timezone)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _seed_active_cell(db: Session, *, badge: str = "2959281396", at: datetime | None = None):
    at = at or datetime(2026, 10, 22, 10, 0, tzinfo=LOCAL_TZ)
    enter = Action(
        code="CELL_ENTER",
        label="Cell entry",
        supplier_device_event="CELL_ENTER",
        state_effect="ENTER",
        oracle_attributes={},
        active=True,
    )
    auto_exit = Action(
        code="DIRECT_OUT_FACTORY",
        label="Direct Out Factory",
        supplier_device_event="DIRECT_OUT_FACTORY",
        state_effect="EXIT",
        oracle_attributes={},
        show_on_terminal=False,
        active=True,
    )
    terminal = Terminal(
        factory_code="ARGANDA",
        terminal_role="CELL",
        code="T0001",
        name="Cell terminal",
        external_device_id="DEVICE-T0001",
        identification_mode="BOTH",
        reporter_id_type="BADGE",
        oracle_attributes={},
        active=True,
    )
    config = FactoryPerimeterSettings(
        factory_code="ARGANDA",
        enabled=True,
        badge_source="EXTERNAL",
        dedup_enabled=True,
        dedup_seconds=5,
        auto_exit_action_code="DIRECT_OUT_FACTORY",
        external_last_log_id=100,
        external_sync_initialized_at=at,
    )
    db.add_all([enter, auto_exit, terminal, config])
    db.flush()
    event = TimeEvent(
        id="cell-enter",
        request_number="BSS-T0001-cell-enter",
        terminal_id=terminal.id,
        action_id=enter.id,
        terminal_code=terminal.code,
        device_id=terminal.external_device_id,
        action_code=enter.code,
        action_label=enter.label,
        supplier_device_event=enter.supplier_device_event,
        state_effect="ENTER",
        reporter_id=badge,
        reporter_id_type="BADGE",
        identification_method="RFID",
        event_datetime=at,
        event_timezone=settings.event_timezone,
        oracle_attributes={},
        delivery_status="PENDING",
        created_at=at,
    )
    db.add(event)
    db.commit()
    return config, terminal, event


def test_external_badge_conversion_is_reversible_for_reader_format():
    assert reader_number_to_attr_value("0582609699") == "602650914"
    assert attr_value_to_reader_number("602650914") == "0582609699"
    assert attr_value_to_reader_number(reader_number_to_attr_value("2959281396")) == "2959281396"


def test_incremental_rows_preserve_log_id_zone_and_badge():
    at = datetime(2026, 10, 22, 11, 0, tzinfo=timezone.utc)
    attr = reader_number_to_attr_value("0582609699")
    rows = external_events_after(40, limit=25, query=lambda cursor, limit: [(41, at, "2", attr)])
    assert rows == [{"log_id": 41, "event_time": at, "zone_code": 2, "reporter_id": "0582609699"}]


def test_current_inside_snapshot_returns_only_valid_inside_badges():
    at = datetime(2026, 10, 22, 11, 0, tzinfo=timezone.utc)
    inside_attr = reader_number_to_attr_value("2959281396")
    outside_attr = reader_number_to_attr_value("0582609699")
    rows = external_inside_snapshot(
        query=lambda watermark: [
            (41, at, 2, inside_attr),
            (42, at, 1, outside_attr),
            (43, at, 2, None),
        ]
    )
    assert rows == [{"log_id": 41, "event_time": at, "zone_code": 2, "reporter_id": "2959281396"}]


def test_unresolved_rows_are_counted_per_movement_not_collapsed_by_null_badge(caplog):
    from app.services.external_perimeter_sync import external_current_states
    at = datetime(2026, 10, 22, 11, 0, tzinfo=timezone.utc)
    rows = external_current_states(max_log_id=10, query=lambda cursor: [
        (1, at, 2, None), (2, at + timedelta(minutes=1), 1, None)
    ])
    assert rows == []
    assert "enter=1 exit=1" in caplog.text


def test_bootstrap_from_empty_local_history_imports_all_current_inside_badges(db, monkeypatch):
    config = FactoryPerimeterSettings(
        factory_code="ARGANDA",
        enabled=True,
        badge_source="EXTERNAL",
        dedup_enabled=True,
        dedup_seconds=5,
        auto_exit_action_code=None,
    )
    db.add(config)
    db.commit()

    first_at = datetime(2026, 10, 22, 8, 0, tzinfo=LOCAL_TZ)
    second_at = datetime(2026, 10, 22, 8, 1, tzinfo=LOCAL_TZ)
    monkeypatch.setattr("app.services.external_perimeter_sync.external_high_watermark", lambda: 500)
    monkeypatch.setattr(
        "app.services.external_perimeter_sync.external_inside_snapshot",
        lambda max_log_id=None: [
            {"log_id": 480, "event_time": first_at, "zone_code": 2, "reporter_id": "2959281396"},
            {"log_id": 490, "event_time": second_at, "zone_code": 2, "reporter_id": "0582609699"},
        ],
    )

    assert sync_external_factory(db, config) == 2
    events = db.scalars(select(FactoryPerimeterEvent).order_by(FactoryPerimeterEvent.event_datetime)).all()
    assert [event.reporter_id for event in events] == ["2959281396", "0582609699"]
    assert {event.direction for event in events} == {"ENTER"}
    assert config.external_last_log_id == 500
    assert config.external_sync_initialized_at is not None
    assert config.external_last_sync_at is not None
    assert config.external_sync_error is None
    assert db.scalar(select(func.count()).select_from(TimeEvent)) == 0


def test_bootstrap_snapshot_is_limited_to_cursor(db, monkeypatch):
    config = FactoryPerimeterSettings(factory_code="ARGANDA", enabled=True, badge_source="EXTERNAL",
        dedup_enabled=True, dedup_seconds=5)
    db.add(config)
    db.commit()
    at = datetime(2026, 10, 22, 8, 0, tzinfo=LOCAL_TZ)
    cursors = []
    monkeypatch.setattr("app.services.external_perimeter_sync.external_high_watermark", lambda: 500)
    monkeypatch.setattr("app.services.external_perimeter_sync.external_inside_snapshot", lambda max_log_id=None: cursors.append(max_log_id) or [
        {"log_id": 499, "event_time": at, "zone_code": 2, "reporter_id": "2959281396"}
    ])
    assert sync_external_factory(db, config) == 1
    assert cursors == [500]
    assert config.external_last_log_id == 500



def test_bootstrap_snapshot_without_external_log_id_is_unique_per_badge(db):
    config = FactoryPerimeterSettings(
        factory_code="ARGANDA", enabled=True, badge_source="EXTERNAL",
        dedup_enabled=False, dedup_seconds=0, auto_exit_action_code=None,
    )
    db.add(config)
    db.flush()
    terminal = ensure_virtual_terminal(db, "ARGANDA")
    at = datetime(2026, 10, 22, 8, 0, tzinfo=LOCAL_TZ)
    first = {"log_id": -1, "event_time": at, "zone_code": 2, "reporter_id": "2959281396"}
    second = {"log_id": -1, "event_time": at, "zone_code": 2, "reporter_id": "0582609699"}

    assert mirror_external_event(db, config, terminal, first) is True
    assert mirror_external_event(db, config, terminal, second) is True
    assert mirror_external_event(db, config, terminal, first) is False
    db.commit()
    events = db.scalars(select(FactoryPerimeterEvent)).all()
    assert len(events) == 2
    assert {event.reporter_id for event in events} == {"2959281396", "0582609699"}

def test_external_exit_is_mirrored_and_closes_active_cell_once(db):
    config, _, _ = _seed_active_cell(db)
    source_terminal = ensure_virtual_terminal(db, "ARGANDA")
    exit_at = datetime(2026, 10, 22, 10, 5, tzinfo=LOCAL_TZ)
    item = {"log_id": 101, "event_time": exit_at, "zone_code": 1, "reporter_id": "2959281396"}

    assert mirror_external_event(db, config, source_terminal, item) is True
    db.commit()

    perimeter = db.scalar(select(FactoryPerimeterEvent))
    assert perimeter is not None
    assert perimeter.direction == "EXIT"
    assert perimeter.terminal_id == source_terminal.id
    assert perimeter.auto_cell_exit_event_id is not None

    cell_events = db.scalars(select(TimeEvent).order_by(TimeEvent.event_datetime)).all()
    assert [event.state_effect for event in cell_events] == ["ENTER", "EXIT"]
    assert cell_events[-1].terminal_code == "T0001"
    stored_exit = cell_events[-1].event_datetime
    if stored_exit.tzinfo is None:
        stored_exit = stored_exit.replace(tzinfo=LOCAL_TZ)
    assert stored_exit == exit_at

    assert mirror_external_event(db, config, source_terminal, item) is False
    db.commit()
    assert db.scalar(select(func.count()).select_from(FactoryPerimeterEvent)) == 1
    assert db.scalar(select(func.count()).select_from(TimeEvent)) == 2


def test_delayed_external_exit_older_than_active_cell_does_not_close_it(db):
    cell_at = datetime(2026, 10, 22, 10, 0, tzinfo=LOCAL_TZ)
    config, _, _ = _seed_active_cell(db, at=cell_at)
    source_terminal = ensure_virtual_terminal(db, "ARGANDA")
    old_exit = cell_at - timedelta(minutes=5)

    assert mirror_external_event(
        db,
        config,
        source_terminal,
        {"log_id": 99, "event_time": old_exit, "zone_code": 1, "reporter_id": "2959281396"},
    ) is True
    db.commit()

    assert db.scalar(select(func.count()).select_from(FactoryPerimeterEvent)) == 1
    assert db.scalar(select(func.count()).select_from(TimeEvent)) == 1
    assert db.scalar(select(TimeEvent).order_by(TimeEvent.event_datetime.desc())).state_effect == "ENTER"


def test_incremental_sync_advances_cursor_and_is_idempotent(db, monkeypatch):
    config, _, _ = _seed_active_cell(db)
    at = datetime(2026, 10, 22, 10, 6, tzinfo=LOCAL_TZ)
    calls = []

    def fake_events(cursor, *, limit=None, query=None):
        calls.append(cursor)
        if cursor == 100:
            return [{"log_id": 101, "event_time": at, "zone_code": 2, "reporter_id": "2959281396"}]
        return []

    monkeypatch.setattr("app.services.external_perimeter_sync.external_events_after", fake_events)
    assert sync_external_factory(db, config) == 1
    assert config.external_last_log_id == 101
    assert config.external_sync_error is None
    assert sync_external_factory(db, config) == 0
    assert calls[:2] == [100, 101]
    assert db.scalar(select(func.count()).select_from(FactoryPerimeterEvent)) == 1


def _state(log_id, at, zone, badge):
    return {"log_id": log_id, "event_time": at, "zone_code": zone, "reporter_id": badge}


def test_incremental_unresolved_event_is_logged_and_cursor_advances(db, monkeypatch, caplog):
    config, _, _ = _seed_active_cell(db)
    at = datetime(2026, 10, 22, 10, 6, tzinfo=LOCAL_TZ)
    monkeypatch.setattr("app.services.external_perimeter_sync.external_events_after", lambda cursor, **kwargs: [
        {"log_id": cursor + 1, "event_time": at, "zone_code": 1, "reporter_id": None}
    ] if cursor == 100 else [])
    assert sync_external_factory(db, config) == 0
    assert config.external_last_log_id == 101
    assert "direction=EXIT" in caplog.text


def test_reconcile_inside_sql_missing_local_creates_enter(db, monkeypatch):
    config, _, _ = _seed_active_cell(db)
    at = datetime(2026, 10, 22, 10, 6, tzinfo=LOCAL_TZ)
    monkeypatch.setattr("app.services.external_perimeter_sync.external_high_watermark", lambda: 200)
    monkeypatch.setattr("app.services.external_perimeter_sync.external_current_states", lambda **kwargs: [
        _state(180, at, 2, "0582609699")
    ])
    assert reconcile_external_factory(db, config) == 1
    event = db.scalar(select(FactoryPerimeterEvent))
    assert (event.reporter_id, event.direction, event.event_datetime) == ("0582609699", "ENTER", at.replace(tzinfo=None))
    assert event.terminal_id == ensure_virtual_terminal(db, "ARGANDA").id


def test_reconcile_outside_creates_exit_and_auto_exits_active_cell_once(db, monkeypatch):
    config, _, _ = _seed_active_cell(db)
    terminal = ensure_virtual_terminal(db, "ARGANDA")
    entered = datetime(2026, 10, 22, 10, 0, tzinfo=LOCAL_TZ)
    exited = entered + timedelta(minutes=5)
    mirror_external_event(db, config, terminal, _state(150, entered, 2, "2959281396"))
    db.commit()
    monkeypatch.setattr("app.services.external_perimeter_sync.external_high_watermark", lambda: 200)
    monkeypatch.setattr("app.services.external_perimeter_sync.external_current_states", lambda **kwargs: [
        _state(180, exited, 1, "2959281396")
    ])
    assert reconcile_external_factory(db, config) == 1
    assert reconcile_external_factory(db, config) == 0
    perimeter = db.scalars(select(FactoryPerimeterEvent).order_by(FactoryPerimeterEvent.event_datetime.desc())).first()
    cell = db.scalars(select(TimeEvent).order_by(TimeEvent.event_datetime.desc())).first()
    assert perimeter.direction == "EXIT" and perimeter.event_datetime == exited.replace(tzinfo=None)
    assert cell.state_effect == "EXIT" and cell.event_datetime == exited.replace(tzinfo=None)
    assert cell.terminal_code == "T0001"
    assert cell.correlation_id == perimeter.correlation_id
    assert db.scalar(select(func.count()).select_from(TimeEvent)) == 2
    assert db.scalar(select(func.count()).select_from(TransmissionAttempt)) == 0


def test_reconcile_old_exit_does_not_close_new_cell_enter(db, monkeypatch):
    config, _, cell_enter = _seed_active_cell(db)
    terminal = ensure_virtual_terminal(db, "ARGANDA")
    mirror_external_event(db, config, terminal, _state(90, cell_enter.event_datetime - timedelta(minutes=10), 2, "2959281396"))
    db.commit()
    old_exit = cell_enter.event_datetime - timedelta(minutes=5)
    monkeypatch.setattr("app.services.external_perimeter_sync.external_high_watermark", lambda: 200)
    monkeypatch.setattr("app.services.external_perimeter_sync.external_current_states", lambda **kwargs: [
        _state(99, old_exit, 1, "2959281396")
    ])
    assert reconcile_external_factory(db, config) == 1
    assert db.scalar(select(func.count()).select_from(TimeEvent)) == 1
    assert db.scalar(select(TimeEvent).order_by(TimeEvent.event_datetime.desc())).state_effect == "ENTER"


def test_reconcile_matching_state_and_sql_only_outside_do_not_write(db, monkeypatch):
    config, _, _ = _seed_active_cell(db)
    terminal = ensure_virtual_terminal(db, "ARGANDA")
    at = datetime(2026, 10, 22, 10, 1, tzinfo=LOCAL_TZ)
    mirror_external_event(db, config, terminal, _state(101, at, 2, "2959281396"))
    db.commit()
    before = db.scalar(select(func.count()).select_from(FactoryPerimeterEvent))
    monkeypatch.setattr("app.services.external_perimeter_sync.external_high_watermark", lambda: 300)
    monkeypatch.setattr("app.services.external_perimeter_sync.external_current_states", lambda **kwargs: [
        _state(101, at, 2, "2959281396"), _state(280, at, 1, "1111111111")
    ])
    assert reconcile_external_factory(db, config) == 0
    assert db.scalar(select(func.count()).select_from(FactoryPerimeterEvent)) == before


def test_reconcile_unresolved_does_not_invent_badge(db, monkeypatch):
    config, _, _ = _seed_active_cell(db)
    monkeypatch.setattr("app.services.external_perimeter_sync.external_high_watermark", lambda: 200)
    monkeypatch.setattr("app.services.external_perimeter_sync.external_current_states", lambda **kwargs: [])
    assert reconcile_external_factory(db, config) == 0
    assert db.scalar(select(func.count()).select_from(FactoryPerimeterEvent)) == 0


def test_reconcile_recovers_incremental_missed_movement_when_mapping_resolves(db, monkeypatch):
    config, _, _ = _seed_active_cell(db)
    at = datetime(2026, 10, 22, 10, 6, tzinfo=LOCAL_TZ)
    monkeypatch.setattr("app.services.external_perimeter_sync.external_events_after", lambda cursor, **kwargs: [
        {"log_id": cursor + 1, "event_time": at, "zone_code": 2, "reporter_id": None}
    ] if cursor == 100 else [])
    assert sync_external_factory(db, config) == 0
    assert config.external_last_log_id == 101
    monkeypatch.setattr("app.services.external_perimeter_sync.external_high_watermark", lambda: 101)
    monkeypatch.setattr("app.services.external_perimeter_sync.external_current_states", lambda **kwargs: [
        _state(101, at, 2, "0582609699")
    ])
    assert reconcile_external_factory(db, config) == 1
    assert db.scalar(select(FactoryPerimeterEvent).where(FactoryPerimeterEvent.reporter_id == "0582609699")).direction == "ENTER"
