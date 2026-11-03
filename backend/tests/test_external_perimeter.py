"""External Arganda SQL Server adapter contract and failure handling."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.external_perimeter import reader_number_to_attr_value, check_external_presence
from test_monitoring import monitor


def test_reader_byte_swap():
    assert reader_number_to_attr_value("0582609699") == "602650914"
    assert reader_number_to_attr_value("0000000000") == "0"
    assert reader_number_to_attr_value("0000000001") == "16777216"
    assert reader_number_to_attr_value("4294967295") == "4294967295"


def test_reader_invalid():
    for value in ("", "-1", "12A", "4294967296", "１２３", "0x10"):
        try:
            reader_number_to_attr_value(value)
            assert False, value
        except ValueError:
            pass


def test_presence_states(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "perimeter_external_max_age_hours", 12)
    now = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
    tz = ZoneInfo(settings.event_timezone)
    inside = (now - timedelta(hours=11)).astimezone(tz).replace(tzinfo=None)
    stale = (now - timedelta(hours=13)).astimezone(tz).replace(tzinfo=None)
    assert check_external_presence("0582609699", now=now, query=lambda badge: (inside, "2"))["status"] == "INSIDE"
    assert check_external_presence("0582609699", now=now, query=lambda badge: (stale, "2"))["status"] == "STALE"
    assert check_external_presence("0582609699", now=now, query=lambda badge: (stale, "1"))["status"] == "OUTSIDE"
    exactly_twelve = (now - timedelta(hours=12)).astimezone(tz).replace(tzinfo=None)
    assert check_external_presence("0582609699", now=now, query=lambda badge: (exactly_twelve, "2"))["status"] == "INSIDE"
    assert check_external_presence("0582609699", now=now, query=lambda badge: (inside, "invalid"))["status"] == "UNKNOWN"
    future = (now + timedelta(minutes=2)).astimezone(tz).replace(tzinfo=None)
    assert check_external_presence("0582609699", now=now, query=lambda badge: (future, "2"))["status"] == "ERROR"
    assert check_external_presence("0582609699", now=now, query=lambda badge: None)["status"] == "UNKNOWN"
    assert check_external_presence("0582609699", now=now, query=lambda badge: (_ for _ in ()).throw(OSError()))["status"] == "ERROR"


def test_presence_classifies_secret_and_query_failures(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services import external_perimeter as external
    monkeypatch.setattr(settings, "perimeter_sqlserver_credentials_file", str(tmp_path / "missing.json"))
    result = external.check_external_presence("1")
    assert (result["status"], result["error_category"]) == ("ERROR", "CREDENTIALS_UNAVAILABLE")
    assert external.check_external_presence("1", query=lambda _: (_ for _ in ()).throw(RuntimeError("private")))["error_category"] == "QUERY_FAILED"


def test_connector_status_and_failure_categories(monkeypatch, tmp_path):
    import json
    from app.core.config import settings
    from app.services import external_perimeter as external
    secret = tmp_path / "credentials.json"
    monkeypatch.setattr(settings, "perimeter_sqlserver_credentials_file", str(secret))
    assert external.connector_status()["error_category"] == "CREDENTIALS_UNAVAILABLE"
    secret.write_text(json.dumps({"server": "sql.example:1433", "database": "SECURITY_DB", "username": "readonly", "password": "never-return"}))
    failed = external.test_external_connection(connect=lambda *a, **k: (_ for _ in ()).throw(Exception("28000 login failed secret")))
    assert failed["error_category"] == "AUTH_FAILED"
    assert "password" not in str(failed).lower() and "never-return" not in str(failed)
    unavailable = external.test_external_connection(connect=lambda *a, **k: (_ for _ in ()).throw(TimeoutError("connect timed out")))
    assert unavailable["error_category"] == "CONNECTION_FAILED"
    class Cursor:
        def execute(self, *_): return self
        def fetchone(self): return (1,)
    class Connection:
        def cursor(self): return Cursor()
        def close(self): pass
    ok = external.test_external_connection(connect=lambda *a, **k: Connection())
    assert ok["reachable"] is True and ok["status"] == "CONNECTED"
    assert ok["database"] == "SECURITY_DB" and ok["server"] == "sql.example:1433"


def test_badge_response_validation_and_zone_code(monkeypatch):
    now = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
    response = check_external_presence("0582609699", now=now, query=lambda badge: (now, "malformed"))
    assert response["status"] == "UNKNOWN" and response["error_category"] == "INVALID_RESPONSE"


def test_admin_external_status_and_badge_test_have_no_bss_side_effects(monitor, monkeypatch):
    from sqlalchemy import func, select
    from app.core import config
    from app.models.perimeter import FactoryPerimeterEvent
    from app.models.time_event import TimeEvent
    from app.routers import perimeter
    client, db = monitor
    status = client.get("/api/v1/admin/perimeter/ARGANDA/external/status")
    assert status.status_code == 200
    assert status.json()["provider"] == "SQLSERVER_SECURITY_DB"
    monkeypatch.setattr(perimeter, "check_external_presence", lambda badge, **kwargs: {
        "status": "INSIDE", "event_time": "2026-10-22T10:00:00+00:00", "zone_code": 2, "error_category": None
    })
    result = client.post("/api/v1/admin/perimeter/ARGANDA/external/test-badge", json={"badge": "1234"})
    assert result.status_code == 200 and result.json()["status"] == "INSIDE"
    assert db.scalar(select(func.count()).select_from(TimeEvent)) == 0
    assert db.scalar(select(func.count()).select_from(FactoryPerimeterEvent)) == 0


def test_security_db_source_clock_correction_applies_before_future_and_freshness_checks(monkeypatch):
    from types import SimpleNamespace
    from app.services.external_perimeter import normalize_security_db_event_time

    enabled = SimpleNamespace(source_clock_correction_enabled=True, source_clock_offset_minutes=60)
    raw = datetime(2026, 11, 3, 12, 42, 13)
    effective, applied = normalize_security_db_event_time(raw, enabled)
    assert effective == raw.replace(tzinfo=ZoneInfo("Europe/Madrid")) - timedelta(hours=1)
    assert applied == 60

    now = effective.astimezone(timezone.utc)
    presence = check_external_presence("0582609699", now=now,
        query=lambda _: (raw, "2"), config=enabled)
    assert presence["status"] == "INSIDE"
    assert presence["source_event_time"].startswith("2026-11-03T12:42:13")
    assert presence["event_time"].startswith("2026-11-03T11:42:13")

    recent_raw = (now - timedelta(hours=11, minutes=59) + timedelta(hours=1)).astimezone(
        ZoneInfo("Europe/Madrid")
    ).replace(tzinfo=None)
    assert check_external_presence("0582609699", now=now,
        query=lambda _: (recent_raw, "2"), config=enabled)["status"] == "INSIDE"
    effective_future = (now + timedelta(minutes=2)).astimezone(
        ZoneInfo("Europe/Madrid")
    ).replace(tzinfo=None)
    future_raw = effective_future + timedelta(minutes=59)
    assert check_external_presence("0582609699", now=now,
        query=lambda _: (future_raw, "2"), config=enabled)["status"] == "INSIDE"


def test_security_db_source_clock_correction_negative_zero_and_dst():
    from types import SimpleNamespace
    from app.services.external_perimeter import normalize_security_db_event_time

    raw_winter = datetime(2026, 1, 15, 12, 0, 0)
    raw_summer = datetime(2026, 7, 15, 12, 0, 0)
    disabled = SimpleNamespace(source_clock_correction_enabled=False, source_clock_offset_minutes=60)
    assert normalize_security_db_event_time(raw_winter, disabled)[0].hour == 12
    assert normalize_security_db_event_time(raw_summer, SimpleNamespace(
        source_clock_correction_enabled=True, source_clock_offset_minutes=0))[0].hour == 12
    negative, applied = normalize_security_db_event_time(raw_winter, SimpleNamespace(
        source_clock_correction_enabled=True, source_clock_offset_minutes=-30))
    assert negative.hour == 12 and negative.minute == 30 and applied == -30


def test_clock_configuration_is_persistent_and_transitions_legacy_history_once(monitor):
    from app.models.perimeter import FactoryPerimeterEvent
    from app.models.terminal import Terminal
    from app.models.time_event import TimeEvent
    from sqlalchemy import func, select

    client, db = monitor
    terminal = Terminal(factory_code="ARGANDA", terminal_role="PERIMETER_BOTH",
        code="P0001", name="External history", external_device_id="P0001",
        identification_mode="RFID", reporter_id_type="BADGE", oracle_attributes={}, active=True)
    db.add(terminal); db.flush()
    raw = datetime(2026, 11, 3, 12, 42, 13, tzinfo=ZoneInfo("Europe/Madrid"))
    event = FactoryPerimeterEvent(id="legacy-source", factory_code="ARGANDA",
        reporter_id="0582609699", terminal_id=terminal.id, direction="ENTER",
        event_datetime=raw, source_system="SQLSERVER_SECURITY_DB",
        source_event_datetime=raw, effective_event_datetime=raw,
        source_clock_correction_applied=False, source_clock_correction_pending=True,
        correlation_id="legacy-correlation", auto_cell_exit_event_id=None)
    db.add(event); db.commit()

    payload = {"enabled": False, "badge_source": "EXTERNAL", "dedup_enabled": True,
        "dedup_seconds": 5, "auto_exit_action_code": None,
        "source_clock_correction_enabled": True, "source_clock_offset_minutes": 60}
    response = client.put("/api/v1/admin/perimeter/ARGANDA", json=payload)
    assert response.status_code == 200
    assert response.json()["source_clock_correction_enabled"] is True
    assert response.json()["source_clock_offset_minutes"] == 60
    db.refresh(event)
    assert event.source_event_datetime.replace(tzinfo=ZoneInfo("Europe/Madrid")) == raw
    assert event.event_datetime.replace(tzinfo=ZoneInfo("Europe/Madrid")) == raw
    assert event.effective_event_datetime.replace(tzinfo=ZoneInfo("Europe/Madrid")) == raw - timedelta(hours=1)
    assert event.source_clock_correction_pending is False
    assert event.source_clock_correction_applied is True

    payload["source_clock_correction_enabled"] = False
    payload["source_clock_offset_minutes"] = 0
    assert client.put("/api/v1/admin/perimeter/ARGANDA", json=payload).status_code == 200
    db.refresh(event)
    assert event.source_event_datetime.replace(tzinfo=ZoneInfo("Europe/Madrid")) == raw
    assert event.effective_event_datetime.replace(tzinfo=ZoneInfo("Europe/Madrid")) == raw - timedelta(hours=1)
    assert db.scalar(select(func.count()).select_from(TimeEvent)) == 0
    assert client.put("/api/v1/admin/perimeter/ARGANDA", json={**payload, "source_clock_offset_minutes": 721}).status_code == 422
