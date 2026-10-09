from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.time_event import TimeEvent
from app.models.transmission_attempt import TransmissionAttempt


@pytest.fixture
def monitor():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        app.dependency_overrides[get_db] = lambda: db
        with TestClient(app) as client:
            yield client, db
        app.dependency_overrides.clear()
    engine.dispose()


def add_event(db, badge, clock, effect, minute):
    timestamp = datetime(2026, 10, 9, 12, minute, tzinfo=timezone.utc)
    event = TimeEvent(
        id=f"{badge}-{clock}-{minute}", request_number=f"BSS-{badge}-{clock}-{minute}",
        terminal_id=1, action_id=1, terminal_code=clock, device_id=f"DEVICE-{clock}",
        action_code=effect, action_label=effect, supplier_device_event=f"BSS-{effect}",
        state_effect=effect, reporter_id=badge, reporter_id_type="BADGE",
        identification_method="KEYPAD", event_datetime=timestamp,
        event_timezone="Europe/Madrid", oracle_attributes={"reason": "meal"},
        delivery_status="PENDING", created_at=timestamp,
    )
    db.add(event)
    db.commit()
    return event


def test_card_state_is_global_before_clock_filter(monitor):
    client, db = monitor
    add_event(db, "001", "A", "ENTER", 0)
    add_event(db, "002", "A", "ENTER", 1)
    add_event(db, "001", "B", "EXIT", 2)
    result = client.get("/api/v1/admin/monitoring/cards?terminal_code=A&worker_state=INSIDE").json()
    assert result["total"] == 1
    assert result["items"][0]["reporter_id"] == "002"
    result = client.get("/api/v1/admin/monitoring/cards?reporter_id=001").json()
    assert result["items"][0]["worker_state"] == "OUTSIDE"
    assert result["items"][0]["event"]["terminal_code"] == "B"


def test_events_filters_and_pagination_preserve_leading_zeros(monitor):
    client, db = monitor
    add_event(db, "001", "A", "ENTER", 0)
    add_event(db, "001", "A", "EXIT", 2)
    add_event(db, "002", "B", "ENTER", 3)
    result = client.get("/api/v1/admin/monitoring/events?terminal_code=A&reporter_id=001&limit=1&offset=1").json()
    assert result["total"] == 2
    assert result["items"][0]["reporter_id"] == "001"
    assert result["items"][0]["state_effect"] == "ENTER"
    # Search characters are literals, not SQL LIKE wildcards.
    assert client.get("/api/v1/admin/monitoring/events?reporter_id=%25").json()["total"] == 0
    result = client.get("/api/v1/admin/monitoring/events?start=2026-10-09T12:01:00Z&end=2026-10-09T12:02:00Z").json()
    assert result["total"] == 1
    assert result["items"][0]["state_effect"] == "EXIT"
    assert client.get("/api/v1/admin/monitoring/events?start=2026-10-10T00:00:00Z&end=2026-10-09T00:00:00Z").status_code == 422


def test_detail_preserves_actual_attempt_payload_and_does_not_write(monitor):
    client, db = monitor
    event = add_event(db, "001", "A", "ENTER", 0)
    actual = {"sourceId": "HISTORICAL-SOURCE", "requestTimestamp": "2026-10-09T12:04:00Z", "timeEvents": [{"reporterId": "001"}]}
    attempt = TransmissionAttempt(
        event_id=event.id, attempt_number=1, started_at=event.event_datetime,
        finished_at=event.event_datetime + timedelta(seconds=1), endpoint="https://example.invalid/timeEventRequests",
        http_status=201, result="SENT", duration_ms=1000,
        request_payload=actual, response_payload={"timeEventRequestId": "42"}, error_message=None,
    )
    db.add(attempt)
    db.commit()
    result = client.get(f"/api/v1/admin/monitoring/events/{event.id}").json()
    assert result["attempts"][0]["request_payload"] == actual
    assert result["attempts"][0]["response_payload"]["timeEventRequestId"] == "42"
    assert "requestTimestamp" not in result["oracle_payload_preview"]
    assert result["oracle_payload_preview"]["timeEvents"][0]["eventDateTime"].endswith("+02:00")
    assert result["event"]["oracle_attributes"] == {"reason": "meal"}
    assert db.scalar(select(func.count()).select_from(TimeEvent)) == 1
    assert db.scalar(select(func.count()).select_from(TransmissionAttempt)) == 1
    assert client.get("/api/v1/admin/monitoring/attempts?terminal_code=A&result=SENT").json()["total"] == 1
    assert client.get("/api/v1/admin/monitoring/attempts?terminal_code=B").json()["total"] == 0


def test_pending_event_has_no_transmission_history(monitor):
    client, db = monitor
    event = add_event(db, "009", "A", "ENTER", 0)
    result = client.get(f"/api/v1/admin/monitoring/events/{event.id}").json()
    assert result["attempts"] == []
    assert result["event"]["delivery_status"] == "PENDING"
    assert client.get("/api/v1/admin/monitoring/events/missing").status_code == 404
