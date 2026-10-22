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
    monkeypatch.setattr(perimeter, "check_external_presence", lambda badge: {
        "status": "INSIDE", "event_time": "2026-10-22T10:00:00+00:00", "zone_code": 2, "error_category": None
    })
    result = client.post("/api/v1/admin/perimeter/ARGANDA/external/test-badge", json={"badge": "1234"})
    assert result.status_code == 200 and result.json()["status"] == "INSIDE"
    assert db.scalar(select(func.count()).select_from(TimeEvent)) == 0
    assert db.scalar(select(func.count()).select_from(FactoryPerimeterEvent)) == 0
