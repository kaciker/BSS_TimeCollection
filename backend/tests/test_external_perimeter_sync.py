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
    _normalize_external_row,
    _snapshot_event_uuid,
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
    at = datetime(2026, 10, 22, 11, 0)
    attr = reader_number_to_attr_value("0582609699")
    rows = external_events_after(at, limit=25, query=lambda *args: [
        ("source-41", "unique-41", 41, at, at, "2", attr)
    ])
    assert rows == [{"source_transaction_id": "source-41", "unique_key": "unique-41",
        "log_id": 41, "source_created_at": at, "event_time": at.replace(tzinfo=LOCAL_TZ),
        "zone_code": 2, "reporter_id": "0582609699"}]


def test_incremental_join_mappings_are_collapsed_and_ambiguous_badges_unresolved(caplog):
    at = datetime(2026, 10, 22, 11, 0)
    attr_a = reader_number_to_attr_value("0582609699")
    attr_b = reader_number_to_attr_value("2959281396")
    rows = external_events_after(at, limit=25, query=lambda *args: [
        ("source-41", "unique-41", 41, at, at, 2, attr_a),
        ("source-41", "unique-41", 41, at, at, 2, attr_a),
        ("source-42", "unique-42", 42, at, at, 1, attr_a),
        ("source-42", "unique-42", 42, at, at, 1, attr_b),
    ])
    assert len(rows) == 2
    assert rows[0]["reporter_id"] == "0582609699"
    assert rows[1]["reporter_id"] is None
    assert "source_transaction_id=source-42" in caplog.text


def test_incremental_rows_are_returned_in_source_pk_order_for_keyset_cursor():
    at = datetime(2026, 10, 22, 11, 0)
    attr = reader_number_to_attr_value("0582609699")
    rows = external_events_after(at, limit=25, query=lambda *args: [
        ("700", "k700", 9, at, at, 2, attr, 2),
        ("12", "k12", 9, at, at, 2, attr, 2),
    ])
    assert [int(row["source_transaction_id"]) for row in rows] == [12, 700]


def test_distinct_source_transactions_with_same_log_id_remain_distinct():
    at = datetime(2026, 10, 22, 11, 0)
    attr = reader_number_to_attr_value("0582609699")
    rows = external_events_after(at, limit=25, query=lambda *args: [
        ("transaction-A", "unique-A", 75523, at, at, 2, attr),
        ("transaction-B", "unique-B", 75523, at + timedelta(seconds=1), at, 2, attr),
    ])
    assert [row["source_transaction_id"] for row in rows] == ["transaction-A", "transaction-B"]
    assert _snapshot_event_uuid("ARGANDA", rows[0]) != _snapshot_event_uuid("ARGANDA", rows[1])


def test_existing_source_transaction_with_legacy_event_id_is_idempotent(db):
    config, _, _ = _seed_active_cell(db)
    terminal = ensure_virtual_terminal(db, "ARGANDA")
    at = datetime(2026, 10, 22, 11, 0, tzinfo=LOCAL_TZ)
    item = {"source_transaction_id": "81003", "unique_key": "u3", "log_id": 78,
            "event_time": at, "zone_code": 2, "reporter_id": "2959281396"}
    legacy = FactoryPerimeterEvent(
        id="legacy-log-id-event", factory_code="ARGANDA", reporter_id="2959281396",
        terminal_id=terminal.id, direction="ENTER", event_datetime=at,
        correlation_id="legacy-correlation", source_system="SQLSERVER_SECURITY_DB",
        source_transaction_id="81003", source_log_id=78, source_unique_key="u3",
    )
    db.add(legacy)
    db.flush()

    assert mirror_external_event(db, config, terminal, item) is False
    db.commit()
    rows = db.scalars(select(FactoryPerimeterEvent).where(
        FactoryPerimeterEvent.source_transaction_id == "81003"
    )).all()
    assert len(rows) == 1
    assert rows[0].id == "legacy-log-id-event"


def test_same_log_id_movements_are_imported_as_distinct_idempotent_events(db):
    config, _, _ = _seed_active_cell(db)
    terminal = ensure_virtual_terminal(db, "ARGANDA")
    at = datetime(2026, 10, 22, 11, 0, tzinfo=LOCAL_TZ)
    first = {"source_transaction_id": "81001", "unique_key": "u1", "log_id": 77,
             "event_time": at, "zone_code": 2, "reporter_id": "2959281396"}
    second = {"source_transaction_id": "81002", "unique_key": "u2", "log_id": 77,
              "event_time": at + timedelta(seconds=1), "zone_code": 2, "reporter_id": "2959281396"}
    assert mirror_external_event(db, config, terminal, first)
    assert mirror_external_event(db, config, terminal, second)
    assert not mirror_external_event(db, config, terminal, first)
    db.commit()
    events = db.scalars(select(FactoryPerimeterEvent).where(
        FactoryPerimeterEvent.source_transaction_id.is_not(None)
    )).all()
    assert {event.source_transaction_id for event in events} == {"81001", "81002"}
    assert {event.source_log_id for event in events} == {77}


def test_current_inside_snapshot_returns_only_valid_inside_badges():
    from app.services.external_perimeter_sync import _CURRENT_INSIDE_SQL
    assert "source_transaction_pk" in _CURRENT_INSIDE_SQL
    at = datetime(2026, 10, 22, 11, 0)
    inside_attr = reader_number_to_attr_value("2959281396")
    outside_attr = reader_number_to_attr_value("0582609699")
    rows = external_inside_snapshot(
        query=lambda *args: [
            ("id-41", "key-41", 41, at, at, 2, inside_attr, 1, False, "CARD-1"),
            ("id-42", "key-42", 42, at, at, 1, outside_attr, 1, False, "CARD-2"),
            ("id-43", "key-43", 43, at, at, 2, None, 1, True, "CARD-3"),
            ("id-44", "key-44", 44, at, at, 2, inside_attr, 1, True, "CARD-1"),
        ]
    )
    assert rows == []  # the latest SQL mapping for CARD-1 is ambiguous


def test_current_state_fails_closed_for_ambiguous_badge_mapping():
    from app.services.external_perimeter_sync import external_current_states
    at = datetime(2026, 10, 22, 11, 0)
    good_attr = reader_number_to_attr_value("2959281396")
    rows = external_current_states(query=lambda: [
        ("20", "ambiguous", 55, at, at, 2, good_attr, 1, False, "CARD-A"),
        ("21", "ambiguous", 56, at + timedelta(minutes=1), at, 1, None, 1, True, "CARD-A"),
        ("30", "good", 57, at, at, 2, reader_number_to_attr_value("0582609699"), 1, False, "CARD-B"),
    ])
    assert [item["reporter_id"] for item in rows] == ["0582609699"]


def test_naive_security_db_datetime_attaches_madrid_and_preserves_instant():
    raw = datetime(2026, 10, 30, 10, 23, 17)
    item = _normalize_external_row(("source-id", "unique", 834140, raw, raw, "2",
                                   reader_number_to_attr_value("2959281396")))
    assert item["event_time"].isoformat() == "2026-10-30T10:23:17+01:00"
    assert item["event_time"].astimezone(timezone.utc).isoformat() == "2026-10-30T09:23:17+00:00"


def test_sql_utc_clock_is_compared_as_madrid_local_wall_time():
    from app.services.external_perimeter_sync import external_source_now
    utc_now = datetime(2026, 10, 30, 9, 23, 17, tzinfo=timezone.utc)
    assert external_source_now(query=lambda: utc_now) == datetime(2026, 10, 30, 10, 23, 17)


def test_unresolved_rows_are_counted_per_movement_not_collapsed_by_null_badge(caplog):
    from app.services.external_perimeter_sync import external_current_states
    at = datetime(2026, 10, 22, 11, 0)
    rows = external_current_states(query=lambda: [
        ("1", "key1", 31, at, at, 2, None), ("2", "key2", 31, at + timedelta(minutes=1), at, 1, None)
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
    monkeypatch.setattr("app.services.external_perimeter_sync.external_source_now", lambda: datetime(2026, 10, 22, 11, 0))
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
    assert config.external_last_log_id is None
    assert config.external_sync_window_from == datetime(2026, 10, 22, 10, 45)
    assert config.external_sync_initialized_at is not None
    assert config.external_last_sync_at is not None
    assert config.external_sync_error is None
    assert db.scalar(select(func.count()).select_from(TimeEvent)) == 0


def test_bootstrap_snapshot_sets_overlap_window(db, monkeypatch):
    config = FactoryPerimeterSettings(factory_code="ARGANDA", enabled=True, badge_source="EXTERNAL",
        dedup_enabled=True, dedup_seconds=5)
    db.add(config)
    db.commit()
    at = datetime(2026, 10, 22, 8, 0, tzinfo=LOCAL_TZ)
    calls = []
    monkeypatch.setattr("app.services.external_perimeter_sync.external_source_now", lambda: datetime(2026, 10, 22, 11, 0))
    monkeypatch.setattr("app.services.external_perimeter_sync.external_inside_snapshot", lambda max_log_id=None: calls.append(max_log_id) or [
        {"log_id": 499, "event_time": at, "zone_code": 2, "reporter_id": "2959281396"}
    ])
    assert sync_external_factory(db, config) == 1
    assert calls == [None]
    assert config.external_last_log_id is None
    assert config.external_sync_window_from == datetime(2026, 10, 22, 10, 45)



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


def test_future_external_exit_is_perimeter_only_and_does_not_create_future_cell_event(db):
    config, _, _ = _seed_active_cell(db)
    terminal = ensure_virtual_terminal(db, "ARGANDA")
    future = datetime.now(timezone.utc) + timedelta(days=2)
    assert mirror_external_event(db, config, terminal, {
        "source_transaction_id": "future-source", "unique_key": "future-key", "log_id": 888,
        "event_time": future, "zone_code": 1, "reporter_id": "2959281396",
    })
    db.commit()
    assert db.scalar(select(func.count()).select_from(FactoryPerimeterEvent)) == 1
    assert db.scalar(select(func.count()).select_from(TimeEvent)) == 1


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


def test_incremental_sync_uses_overlap_window_and_is_idempotent(db, monkeypatch):
    config, _, _ = _seed_active_cell(db)
    at = datetime(2026, 10, 22, 10, 6, tzinfo=LOCAL_TZ)
    calls = []
    source_created = datetime(2026, 10, 22, 10, 6)
    item = {"source_transaction_id": "source-101", "unique_key": "key-101", "log_id": 101,
            "source_created_at": source_created, "event_time": at, "zone_code": 2, "reporter_id": "2959281396"}

    def fake_events(window, after_created, after_id, *, limit=None, query=None):
        calls.append((window, after_created, after_id))
        if after_created is None:
            return [item]
        return []

    monkeypatch.setattr("app.services.external_perimeter_sync.external_events_after", fake_events)
    monkeypatch.setattr("app.services.external_perimeter_sync.external_source_now", lambda: datetime(2026, 10, 22, 10, 7))
    assert sync_external_factory(db, config) == 1
    assert config.external_sync_cursor_created_at is None
    assert config.external_sync_window_from == datetime(2026, 10, 22, 9, 52)
    assert config.external_sync_error is None
    assert sync_external_factory(db, config) == 0
    assert len(calls) == 2
    assert db.scalar(select(func.count()).select_from(FactoryPerimeterEvent)) == 1


def test_transition_from_log_id_cursor_uses_last_sync_plus_overlap(db, monkeypatch):
    config, _, _ = _seed_active_cell(db)
    previous_sync = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
    config.external_last_sync_at = previous_sync
    seen = []
    monkeypatch.setattr("app.services.external_perimeter_sync.external_source_now", lambda: datetime(2026, 10, 22, 10, 5))
    monkeypatch.setattr("app.services.external_perimeter_sync.external_events_after", lambda window, *args, **kwargs:
        seen.append(window) or [])
    sync_external_factory(db, config)
    assert seen == [datetime(2026, 10, 22, 10, 45)]


def test_incremental_sync_reaches_ten_batches_and_resumes_same_keyset(db, monkeypatch):
    config, _, _ = _seed_active_cell(db)
    monkeypatch.setattr("app.services.external_perimeter_sync.settings.perimeter_external_sync_batch_size", 1)
    batch_size = 1
    if batch_size < 1:
        pytest.skip("invalid configured batch size")
    calls = []
    monkeypatch.setattr("app.services.external_perimeter_sync.external_source_now", lambda: datetime(2026, 10, 22, 10, 7))
    def fake_events(window, after_created, after_id, *, limit=None, query=None):
        calls.append((after_created, after_id))
        if len(calls) <= 10:
            source_id = str(len(calls))
            return [{"source_transaction_id": source_id, "source_created_at": datetime(2026, 10, 22, 10, 6),
                     "log_id": 777, "event_time": datetime(2026, 10, 22, 10, 6, tzinfo=LOCAL_TZ),
                     "zone_code": 2, "reporter_id": f"badge-{len(calls)}", "_page_full": True}]
        return []
    monkeypatch.setattr("app.services.external_perimeter_sync.external_events_after", fake_events)
    sync_external_factory(db, config)
    assert config.external_sync_cursor_created_at == datetime(2026, 10, 22, 10, 6)
    assert config.external_sync_cursor_transaction_id == "10"
    assert len(calls) == 10


def test_initial_catchup_uses_ten_batch_bound_without_losing_cursor(db, monkeypatch):
    config = FactoryPerimeterSettings(factory_code="ARGANDA", enabled=True, badge_source="EXTERNAL")
    db.add(config)
    db.commit()
    monkeypatch.setattr("app.services.external_perimeter_sync.external_source_now", lambda: datetime(2026, 10, 22, 11, 0))
    monkeypatch.setattr("app.services.external_perimeter_sync.external_inside_snapshot", lambda **kwargs: [])
    assert sync_external_factory(db, config) == 0
    assert config.external_sync_window_from == datetime(2026, 10, 22, 10, 45)
    calls = []
    monkeypatch.setattr("app.services.external_perimeter_sync.settings.perimeter_external_sync_batch_size", 1)
    def fake_events(window, after_created, after_id, *, limit=None, query=None):
        calls.append((after_created, after_id))
        current = len(calls)
        return [{"source_transaction_id": str(current), "source_created_at": datetime(2026, 10, 22, 10, 50),
                 "log_id": 8, "event_time": datetime(2026, 10, 22, 10, 50, tzinfo=LOCAL_TZ),
                 "zone_code": 2, "reporter_id": None, "_page_full": True}]
    monkeypatch.setattr("app.services.external_perimeter_sync.external_events_after", fake_events)
    assert sync_external_factory(db, config) == 0
    assert len(calls) == 10
    assert config.external_sync_cursor_transaction_id == "10"


def _state(log_id, at, zone, badge):
    return {"log_id": log_id, "event_time": at, "zone_code": zone, "reporter_id": badge}


def test_incremental_unresolved_event_is_logged_and_cursor_advances(db, monkeypatch, caplog):
    config, _, _ = _seed_active_cell(db)
    at = datetime(2026, 10, 22, 10, 6, tzinfo=LOCAL_TZ)
    monkeypatch.setattr("app.services.external_perimeter_sync.external_source_now", lambda: datetime(2026, 10, 22, 10, 7))
    monkeypatch.setattr("app.services.external_perimeter_sync.external_events_after", lambda *args, **kwargs: [
        {"source_transaction_id": "unresolved-101", "log_id": 101, "event_time": at,
         "source_created_at": datetime(2026, 10, 22, 10, 6), "zone_code": 1, "reporter_id": None}
    ] if args[1] is None else [])
    assert sync_external_factory(db, config) == 0
    assert config.external_sync_cursor_transaction_id is None
    assert "direction=EXIT" in caplog.text


def test_reconcile_inside_sql_missing_local_creates_enter(db, monkeypatch):
    config, _, _ = _seed_active_cell(db)
    at = datetime(2026, 10, 22, 10, 6, tzinfo=LOCAL_TZ)
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
    monkeypatch.setattr("app.services.external_perimeter_sync.external_current_states", lambda **kwargs: [
        _state(101, at, 2, "2959281396"), _state(280, at, 1, "1111111111")
    ])
    assert reconcile_external_factory(db, config) == 0
    assert db.scalar(select(func.count()).select_from(FactoryPerimeterEvent)) == before


def test_reconcile_unresolved_does_not_invent_badge(db, monkeypatch):
    config, _, _ = _seed_active_cell(db)
    monkeypatch.setattr("app.services.external_perimeter_sync.external_current_states", lambda **kwargs: [])
    assert reconcile_external_factory(db, config) == 0
    assert db.scalar(select(func.count()).select_from(FactoryPerimeterEvent)) == 0


def test_reconcile_recovers_incremental_missed_movement_when_mapping_resolves(db, monkeypatch):
    config, _, _ = _seed_active_cell(db)
    at = datetime(2026, 10, 22, 10, 6, tzinfo=LOCAL_TZ)
    monkeypatch.setattr("app.services.external_perimeter_sync.external_source_now", lambda: datetime(2026, 10, 22, 10, 7))
    monkeypatch.setattr("app.services.external_perimeter_sync.external_events_after", lambda *args, **kwargs: [
        {"source_transaction_id": "101", "source_created_at": datetime(2026, 10, 22, 10, 6),
         "log_id": 101, "event_time": at, "zone_code": 2, "reporter_id": None}
    ] if args[1] is None else [])
    assert sync_external_factory(db, config) == 0
    assert config.external_last_log_id == 100
    monkeypatch.setattr("app.services.external_perimeter_sync.external_current_states", lambda **kwargs: [
        _state(101, at, 2, "0582609699")
    ])
    assert reconcile_external_factory(db, config) == 1
    assert db.scalar(select(FactoryPerimeterEvent).where(FactoryPerimeterEvent.reporter_id == "0582609699")).direction == "ENTER"
