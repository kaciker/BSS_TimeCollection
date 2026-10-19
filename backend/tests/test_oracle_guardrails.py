from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import worker
from app.db.base import Base
from app.models.time_event import TimeEvent
from app.schemas.admin import ActionCreate, TerminalCreate
from app.schemas.terminal import ScanRequest


def test_oracle_field_limits_are_enforced_before_capture():
    with pytest.raises(ValidationError):
        TerminalCreate(name="Clock", external_device_id="D" * 41)

    with pytest.raises(ValidationError):
        ActionCreate(
            code="START",
            label="Start",
            supplier_device_event="E" * 41,
            state_effect="ENTER",
        )

    with pytest.raises(ValidationError):
        ScanRequest(reporter_id="R" * 81, identification_method="KEYPAD")

    assert TerminalCreate(name="Clock", external_device_id="D" * 40).external_device_id == "D" * 40
    assert ActionCreate(
        code="START",
        label="Start",
        supplier_device_event="E" * 40,
        state_effect="ENTER",
    ).supplier_device_event == "E" * 40
    assert ScanRequest(reporter_id="R" * 80, identification_method="KEYPAD").reporter_id == "R" * 80


def test_stale_sending_event_requires_reconciliation(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    old_attempt = datetime.now(timezone.utc) - timedelta(minutes=10)

    with Session(engine) as db:
        db.add(
            TimeEvent(
                id="stale-send",
                request_number="BSS-stale-send",
                terminal_id=1,
                action_id=1,
                terminal_code="T0001",
                device_id="CLOCK-01",
                action_code="START",
                action_label="Start",
                supplier_device_event="BSS_START",
                state_effect="ENTER",
                reporter_id="0001",
                reporter_id_type="BADGE",
                identification_method="KEYPAD",
                event_datetime=old_attempt,
                event_timezone="Europe/Madrid",
                oracle_attributes={},
                delivery_status="SENDING",
                attempt_count=1,
                last_attempt_at=old_attempt,
                next_attempt_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

    monkeypatch.setattr(worker, "SessionLocal", lambda: Session(engine))
    monkeypatch.setattr(worker.settings, "worker_stale_sending_seconds", 60)
    worker.recover_stale_events()

    with Session(engine) as db:
        event = db.get(TimeEvent, "stale-send")
        assert event.delivery_status == "UNKNOWN"
        assert event.next_attempt_at is None

    engine.dispose()
