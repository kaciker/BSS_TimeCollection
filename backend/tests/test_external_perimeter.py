"""External Arganda SQL Server adapter contract and failure handling."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.external_perimeter import reader_number_to_attr_value, check_external_presence


def test_reader_byte_swap():
    assert reader_number_to_attr_value("0582609699") == "602650914"
    assert reader_number_to_attr_value("0000000000") == "0"


def test_reader_invalid():
    for value in ("", "-1", "12A", "4294967296", "１２３"):
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
    assert check_external_presence("0582609699", now=now, query=lambda badge: (inside, 2))["status"] == "INSIDE"
    assert check_external_presence("0582609699", now=now, query=lambda badge: (stale, 2))["status"] == "STALE"
    assert check_external_presence("0582609699", now=now, query=lambda badge: (stale, 1))["status"] == "OUTSIDE"
    assert check_external_presence("0582609699", now=now, query=lambda badge: None)["status"] == "UNKNOWN"
    assert check_external_presence("0582609699", now=now, query=lambda badge: (_ for _ in ()).throw(OSError()))["status"] == "ERROR"
