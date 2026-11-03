import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.integrations.oracle.client import DeliveryResult, OracleClient
from app.models.time_event import TimeEvent
from app.models.transmission_attempt import TransmissionAttempt
from app.services import oracle_delivery


def make_event(event_id="selected", **overrides):
    values = dict(
        id=event_id,
        request_number=f"BSS-{event_id}",
        terminal_id=1,
        action_id=1,
        terminal_code="T-CELL",
        device_id="local-device",
        action_code="START",
        action_label="Start",
        supplier_device_event="BSS_START",
        oracle_supplier_event="HUT_TCD_SUPP1_IN_2",
        state_effect="ENTER",
        reporter_id="raw-badge",
        reporter_id_type="BADGE",
        identification_method="RFID",
        person_id="23703",
        event_datetime=datetime(2026, 11, 3, 12, tzinfo=timezone.utc),
        event_timezone="UTC",
        oracle_payroll_time_type="Workshop Entry ES",
        oracle_attributes={},
        workshop_code="local-W",
        subworkshop_code="local-S",
        project_line_code="local-P",
        oracle_work_area_code="439",
        oracle_machine_code="4391",
        oracle_cell_code="54Q",
        delivery_status="PENDING",
        attempt_count=0,
        created_at=datetime(2026, 11, 3, 12, tzinfo=timezone.utc),
    )
    values.update(overrides)
    return TimeEvent(**values)


@pytest.fixture
def db_factory(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = lambda: Session(engine, expire_on_commit=False)
    monkeypatch.setattr(oracle_delivery, "SessionLocal", factory)
    with factory() as db:
        db.add_all([make_event("selected"), make_event("other")])
        db.commit()
    try:
        yield factory
    finally:
        engine.dispose()


def test_real_nested_201_response_extracts_ids_and_preserves_audit_fields(monkeypatch):
    from app.integrations.oracle import client as oracle

    fixture = json.loads((__import__("pathlib").Path(__file__).parent / "fixtures/oracle_201_nested.json").read_text())
    calls = []

    class Response:
        status_code = 201
        text = json.dumps(fixture)
        def json(self): return fixture

    class HttpClient:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def post(self, *args, **kwargs):
            calls.append((args, kwargs))
            return Response()

    ticks = iter([10.0, 10.021])
    monkeypatch.setattr(oracle.httpx, "Client", HttpClient)
    monkeypatch.setattr(oracle, "monotonic", lambda: next(ticks))
    result = OracleClient().send(make_event())
    assert result.result == "SENT"
    assert result.status_code == 201
    assert result.duration_ms == 21
    assert result.oracle_request_id == 300001304086023
    assert result.oracle_event_id == 300001304086024
    assert result.response_payload == fixture
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("body", "request_id", "event_id"),
    [
        ({"timeEventRequestId": 1, "timeEvents": [{"timeEventId": 2}]}, 1, 2),
        ({"timeEventRequestId": 3, "items": [{"timeEventId": 4}]}, 3, 4),
        ({"timeEvents": {"items": [{"id": 999}]}}, None, None),
    ],
)
def test_oracle_event_id_extraction_supports_known_shapes_without_guessing(body, request_id, event_id):
    from app.integrations.oracle.client import _extract_event_id

    assert _extract_event_id(body) == event_id
    assert (body.get("timeEventRequestId")) == request_id


class FakeClient:
    endpoint = "https://oracle.invalid/timeEventRequests"

    def __init__(self, result=None):
        self.calls = []
        self.result = result or DeliveryResult(
            "SENT", False, False, 201, 8,
            {"requestNumber": "BSS-selected"},
            {"timeEventRequestId": "42", "timeEvents": {"items": [{"timeEventId": "84"}]}},
            None, "42", "84",
        )

    def build_payload(self, event):
        return OracleClient().build_payload(event)

    def send(self, event):
        self.calls.append(event.id)
        return self.result


def test_dry_run_returns_exact_payload_without_http_or_database_writes(db_factory):
    client = FakeClient()
    with db_factory() as db:
        before = db.scalar(select(func.count()).select_from(TransmissionAttempt))
        event_before = db.get(TimeEvent, "selected")
        snapshot = (event_before.delivery_status, event_before.attempt_count, event_before.last_attempt_at)
    result = oracle_delivery.send_one_event("selected", send=False, client=client, session_factory=db_factory)
    with db_factory() as db:
        event_after = db.get(TimeEvent, "selected")
        assert db.scalar(select(func.count()).select_from(TransmissionAttempt)) == before
        assert (event_after.delivery_status, event_after.attempt_count, event_after.last_attempt_at) == snapshot
        assert db.get(TimeEvent, "other").delivery_status == "PENDING"
    assert client.calls == []
    assert result["payload"]["requestNumber"] == "BSS-selected"


def test_explicit_event_id_sends_only_selected_and_audits_ids_once(db_factory):
    assert settings.oracle_enabled is False
    client = FakeClient()
    result = oracle_delivery.send_one_event(
        "selected", send=True, confirm_request_number="BSS-selected", client=client, session_factory=db_factory
    )
    with db_factory() as db:
        selected = db.get(TimeEvent, "selected")
        other = db.get(TimeEvent, "other")
        attempts = db.scalars(select(TransmissionAttempt)).all()
        assert selected.delivery_status == "SENT"
        assert selected.sent_at is not None
        assert selected.oracle_request_id == "42"
        assert selected.oracle_event_id == "84"
        assert len(attempts) == 1
        assert attempts[0].request_payload == client.result.request_payload
        assert attempts[0].response_payload == client.result.response_payload
        assert attempts[0].http_status == 201 and attempts[0].duration_ms == 8
        assert attempts[0].oracle_request_id == "42" and attempts[0].oracle_event_id == "84"
        assert attempts[0].retryable is False and attempts[0].ambiguous is False
        assert other.delivery_status == "PENDING" and other.attempt_count == 0
    assert client.calls == ["selected"]
    assert result["attempt_id"] is not None


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"delivery_status": "LOCAL_ONLY"}, "LOCAL_ONLY"),
        ({"oracle_payroll_time_type": None}, "PayrollTimeType"),
        ({"oracle_work_area_code": None}, "WORK_AREA"),
        ({"oracle_machine_code": None}, "MACHINE"),
        ({"oracle_cell_code": None}, "CELL"),
        ({"oracle_payroll_time_type": "Unknown type"}, "not in the HR-Path catalogue"),
        ({"oracle_machine_code": "4399"}, "not in the HR-Path catalogue"),
        ({"oracle_cell_code": "54Q", "oracle_machine_code": "4393"}, "does not belong to MACHINE"),
        ({"person_id": None}, "Person ID"),
        ({"delivery_status": "SENT"}, "SENT"),
        ({"delivery_status": "UNKNOWN"}, "UNKNOWN"),
        ({"oracle_supplier_event": "wrong"}, "supplier event/direction"),
        ({"request_number": ""}, "requestNumber"),
    ],
)
def test_one_event_refuses_blocked_events_without_sending(db_factory, overrides, match):
    with db_factory() as db:
        event = db.get(TimeEvent, "selected")
        for key, value in overrides.items():
            setattr(event, key, value)
        db.commit()
    client = FakeClient()
    with pytest.raises(ValueError, match=match):
        oracle_delivery.send_one_event(
            "selected", send=True, confirm_request_number="BSS-selected", client=client, session_factory=db_factory
        )
    assert client.calls == []


def test_send_requires_exact_request_number_confirmation(db_factory):
    client = FakeClient()
    with pytest.raises(ValueError, match="exactly match"):
        oracle_delivery.send_one_event(
            "selected", send=True, confirm_request_number="wrong", client=client, session_factory=db_factory
        )
    assert client.calls == []
    with db_factory() as db:
        event = db.get(TimeEvent, "selected")
        assert event.delivery_status == "PENDING" and event.attempt_count == 0


def test_explicit_send_refuses_when_normal_oracle_worker_is_enabled(db_factory, monkeypatch):
    monkeypatch.setattr(settings, "oracle_enabled", True)
    client = FakeClient()
    with pytest.raises(ValueError, match="ORACLE_ENABLED=false"):
        oracle_delivery.send_one_event(
            "selected", send=True, confirm_request_number="BSS-selected", client=client, session_factory=db_factory
        )
    assert client.calls == []


def test_missing_event_is_refused(db_factory):
    with pytest.raises(ValueError, match="does not exist"):
        oracle_delivery.send_one_event("missing", send=False, client=FakeClient(), session_factory=db_factory)


def test_ambiguous_delivery_stays_unknown_and_is_never_replayed(db_factory):
    result = DeliveryResult(
        "UNKNOWN", False, True, 504, 9, {"requestNumber": "BSS-selected"}, {"error": "timeout"},
        "ambiguous", None, None,
    )
    client = FakeClient(result)
    oracle_delivery.send_one_event(
        "selected", send=True, confirm_request_number="BSS-selected", client=client, session_factory=db_factory
    )
    with db_factory() as db:
        event = db.get(TimeEvent, "selected")
        attempt = db.scalar(select(TransmissionAttempt))
        assert event.delivery_status == "UNKNOWN"
        assert attempt.ambiguous is True and attempt.retryable is False
    with pytest.raises(ValueError, match="UNKNOWN"):
        oracle_delivery.send_one_event(
            "selected", send=True, confirm_request_number="BSS-selected", client=client, session_factory=db_factory
        )
    assert client.calls == ["selected"]


def test_unhandled_one_event_failure_is_audited_unknown_without_replay(db_factory):
    class ExplodingClient(FakeClient):
        def send(self, event):
            self.calls.append(event.id)
            raise RuntimeError("connection ended after request may have been written")

    client = ExplodingClient()
    result = oracle_delivery.send_one_event(
        "selected", send=True, confirm_request_number="BSS-selected", client=client, session_factory=db_factory
    )
    with db_factory() as db:
        event = db.get(TimeEvent, "selected")
        attempt = db.scalar(select(TransmissionAttempt))
        assert event.delivery_status == "UNKNOWN"
        assert attempt.result == "UNKNOWN" and attempt.ambiguous is True and attempt.retryable is False
        assert attempt.request_payload["requestNumber"] == "BSS-selected"
    with pytest.raises(ValueError, match="UNKNOWN"):
        oracle_delivery.send_one_event(
            "selected", send=True, confirm_request_number="BSS-selected", client=client, session_factory=db_factory
        )
    assert client.calls == ["selected"]
    assert result["delivery_status"] == "UNKNOWN"


def test_worker_skips_unready_pending_event_and_leaves_it_untouched(db_factory, monkeypatch):
    from app import worker
    with db_factory() as db:
        event=db.get(TimeEvent,"other")
        event.oracle_cell_code=None
        db.commit()
    monkeypatch.setattr(worker,"SessionLocal",db_factory)
    assert worker.claim_next_event() == "selected"
    with db_factory() as db:
        assert db.get(TimeEvent,"other").delivery_status == "PENDING"
