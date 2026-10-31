from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import worker
from app.db.base import Base
from app.integrations.oracle.client import DeliveryResult
from app.models.time_event import TimeEvent
from app.models.transmission_attempt import TransmissionAttempt


@pytest.fixture
def delivery_db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(worker, "SessionLocal", lambda: Session(engine))
    try:
        yield engine
    finally:
        engine.dispose()


def make_event(event_id, created_at, **overrides):
    values = {
        "id": event_id,
        "request_number": f"BSS-{event_id}",
        "terminal_id": 1,
        "action_id": 1,
        "terminal_code": "T-SYNTHETIC",
        "device_id": "D-SYNTHETIC",
        "action_code": "START",
        "action_label": "Start",
        "supplier_device_event": "BSS_START",
        "oracle_supplier_event": "HUT_TCD_SUPP1_IN_2",
        "state_effect": "ENTER",
        "reporter_id": "local-badge",
        "reporter_id_type": "BADGE",
        "identification_method": "RFID",
        "person_id": "SYNTHETIC-PERSON",
        "event_datetime": created_at,
        "event_timezone": "Europe/Madrid",
        "oracle_attributes": {},
        "workshop_code": "W1",
        "subworkshop_code": "S1",
        "project_line_code": "P1",
        "delivery_status": "PENDING",
        "attempt_count": 0,
        "created_at": created_at,
    }
    values.update(overrides)
    return TimeEvent(**values)


def test_claims_events_in_capture_order_and_enforces_unique_local_request_number(delivery_db):
    now = datetime.now(timezone.utc)
    with Session(delivery_db) as db:
        db.add_all([
            make_event("later", now, request_number="BSS-DUPLICATE"),
            make_event("earlier", now - timedelta(seconds=5), request_number="BSS-EARLIER"),
        ])
        db.commit()

    assert worker.claim_next_event() == "earlier"
    assert worker.claim_next_event() == "later"

    with Session(delivery_db) as db:
        db.add(make_event("duplicate", now + timedelta(seconds=1), request_number="BSS-DUPLICATE"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


@pytest.mark.parametrize(("result", "expected_status", "retryable"), [
    ("RETRY", "RETRY", True),
    ("REJECTED", "REJECTED", False),
    ("UNKNOWN", "UNKNOWN", False),
    ("SENT", "SENT", False),
])
def test_delivery_records_attempt_audit_and_updates_queue_state(
    delivery_db, monkeypatch, result, expected_status, retryable
):
    now = datetime.now(timezone.utc)
    with Session(delivery_db) as db:
        event = make_event("audit", now, delivery_status="SENDING", attempt_count=2)
        db.add(event)
        db.commit()

    payload = {"requestNumber": "BSS-audit", "synthetic": True}
    response_payload = {"timeEventRequestId": 42, "synthetic": True} if result == "SENT" else {"error": "synthetic"}
    delivery_result = DeliveryResult(
        result=result,
        retryable=retryable,
        ambiguous=result == "UNKNOWN",
        status_code=201 if result == "SENT" else 503 if retryable else 400 if result == "REJECTED" else None,
        duration_ms=12,
        request_payload=payload,
        response_payload=response_payload,
        error_message="synthetic response" if result != "SENT" else None,
        oracle_request_id="42" if result == "SENT" else None,
        oracle_event_id="84" if result == "SENT" else None,
    )

    class FakeClient:
        endpoint = "https://oracle.invalid/mock"
        def send(self, _event): return delivery_result

    monkeypatch.setattr(worker, "update_runtime_metrics", lambda **_kwargs: None)
    worker.deliver("audit", FakeClient())

    with Session(delivery_db) as db:
        event = db.get(TimeEvent, "audit")
        attempt = db.scalar(select(TransmissionAttempt).where(TransmissionAttempt.event_id == "audit"))
        assert event.delivery_status == expected_status
        assert attempt is not None
        assert attempt.attempt_number == 2
        assert attempt.request_payload == payload
        assert attempt.response_payload == response_payload
        assert attempt.http_status == delivery_result.status_code
        if result == "RETRY":
            assert event.next_attempt_at is not None
        else:
            assert event.next_attempt_at is None
        if result == "SENT":
            assert event.oracle_request_id == "42"
            assert event.oracle_event_id == "84"
            assert event.sent_at is not None
