from datetime import datetime, timezone

import os
import threading
import uuid

import pytest
from sqlalchemy import create_engine, insert, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.domain.enums import DeliveryStatus
from app.integrations.oracle.client import DeliveryResult
from app.models import Action, Factory, OracleCell, OracleMachine, OraclePayrollTimeType, OracleWorkArea, Terminal, TimeEvent
from app.models.oracle_mapping_recovery import OracleMappingRecoveryAudit
from app.models.terminal import terminal_actions
from app.models.transmission_attempt import TransmissionAttempt
from app.services.oracle_mapping_recovery import recover_pending_action_mappings

NOW = datetime(2026, 11, 6, 8, tzinfo=timezone.utc)


@pytest.fixture

def db_factory(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    from app import worker
    monkeypatch.setattr(worker, "SessionLocal", factory)
    with Session(engine) as db:
        db.add_all([
            Factory(id=1, code="F1", name="Synthetic factory", timezone="UTC", active=True),
            OracleWorkArea(code="W1", description="Work area", active=True, source_reference="HR-Path verified"),
            OracleMachine(code="M1", description="Machine", work_area_code="W1", active=True),
            OracleCell(code="C1", description="Cell", machine_code="M1", active=True),
            OraclePayrollTimeType(code="Approved type", active=True, source_reference="HR-Path verified"),
            OraclePayrollTimeType(code="Inactive type", active=False, source_reference="HR-Path verified"),
        ])
        db.flush()
        action = Action(id=1, code="Synthetic EXIT", label="Synthetic EXIT", supplier_device_event="direct_exit", oracle_supplier_event="HUT_TCD_SUPP1_OUT_2", state_effect="EXIT", oracle_payroll_time_type="Approved type", oracle_attributes={}, visual_key=None, display_order=1, requires_subaction=False, show_on_terminal=True, active=True)
        terminal = Terminal(id=1, factory_code="F1", terminal_role="CELL", code="T0001", name="Synthetic cell", external_device_id="D0001", identification_mode="RFID", reporter_id_type="BADGE", oracle_attributes={}, project_line_id=None, active=True)
        db.add_all([action, terminal])
        db.flush()
        db.execute(insert(terminal_actions).values(terminal_id=terminal.id, action_id=action.id))
        db.commit()
    try:
        yield factory
    finally:
        engine.dispose()


def add_event(factory, event_id="e1", **overrides):
    values = dict(
        id=event_id, request_number=f"BSS-{event_id}", terminal_id=1, action_id=1,
        correlation_id="correlation-1", terminal_code="T0001", device_id="D0001",
        action_code="Synthetic EXIT", action_label="Synthetic EXIT", supplier_device_event="direct_exit",
        oracle_supplier_event="HUT_TCD_SUPP1_OUT_2", state_effect="EXIT", reporter_id="badge-1",
        reporter_id_type="BADGE", identification_method="RFID", person_id="1234",
        oracle_reporter_id="1234", oracle_reporter_id_type="PERSON", event_datetime=NOW,
        event_timezone="Europe/Madrid", oracle_payroll_time_type=None,
        oracle_mapping_error="PayrollTimeType missing", oracle_attributes={"keep": "value"},
        workshop_code="439", subworkshop_code="439.1", project_line_code="P24",
        oracle_work_area_code="W1", oracle_machine_code="M1", oracle_cell_code="C1",
        delivery_status="PENDING", attempt_count=0, created_at=NOW,
    )
    values.update(overrides)
    with factory() as db:
        event = TimeEvent(**values)
        db.add(event)
        db.commit()
    return event_id


def test_valid_null_payroll_mapping_recovers_with_audit_and_preserves_identity(db_factory):
    event_id = add_event(db_factory)
    with db_factory() as db:
        assert recover_pending_action_mappings(db, now=NOW) == 1
        db.commit()
    with db_factory() as db:
        event = db.get(TimeEvent, event_id)
        audit = db.scalar(select(OracleMappingRecoveryAudit).where(OracleMappingRecoveryAudit.event_id == event_id))
        assert event.oracle_payroll_time_type == "Approved type"
        assert event.oracle_mapping_error is None
        assert event.id == event_id and event.request_number == f"BSS-{event_id}"
        assert event.person_id == "1234" and event.event_datetime.replace(tzinfo=timezone.utc) == NOW
        assert event.terminal_code == "T0001" and event.correlation_id == "correlation-1"
        assert event.oracle_attributes == {"keep": "value"}
        assert event.delivery_status == "PENDING" and event.attempt_count == 0
        assert audit.field_name == "oracle_payroll_time_type"
        assert audit.previous_value is None and audit.new_value == "Approved type"
        assert audit.source_action_id == 1 and audit.source_action_code == "Synthetic EXIT"
        assert audit.mapping_reference == "HR-Path verified" and "no delivery attempt" in audit.recovery_reason
        assert db.scalar(select(TransmissionAttempt.id).where(TransmissionAttempt.event_id == event_id)) is None


def test_repeat_is_idempotent_and_never_overwrites_non_null_history(db_factory):
    first = add_event(db_factory, "first")
    second = add_event(db_factory, "second", oracle_payroll_time_type="Historical value")
    with db_factory() as db:
        assert recover_pending_action_mappings(db, now=NOW) == 1
        db.commit()
    with db_factory() as db:
        assert recover_pending_action_mappings(db, now=NOW) == 0
        db.commit()
        assert db.get(TimeEvent, second).oracle_payroll_time_type == "Historical value"
        assert len(db.scalars(select(OracleMappingRecoveryAudit)).all()) == 1


@pytest.mark.parametrize("overrides", [
    {"attempt_count": 1}, {"last_attempt_at": NOW}, {"sent_at": NOW},
    {"oracle_request_id": "request-id"}, {"oracle_event_id": "event-id"},
    {"person_id": None}, {"oracle_cell_code": "inactive-or-missing"},
    {"delivery_status": "SENT"}, {"delivery_status": "SENDING"},
    {"delivery_status": "UNKNOWN"}, {"delivery_status": "REJECTED"},
    {"delivery_status": "LOCAL_ONLY"},
])
def test_unsafe_or_unready_event_is_untouched(db_factory, overrides):
    event_id = add_event(db_factory, **overrides)
    with db_factory() as db:
        assert recover_pending_action_mappings(db, now=NOW) == 0
        db.commit()
        event = db.get(TimeEvent, event_id)
        assert event.oracle_payroll_time_type is None
        assert event.oracle_mapping_error == "PayrollTimeType missing"
        assert db.scalars(select(OracleMappingRecoveryAudit)).all() == []


def test_action_not_updated_after_capture_is_not_a_recovery_source(db_factory):
    event_id = add_event(db_factory)
    with db_factory() as db:
        db.get(Action, 1).updated_at = NOW
        db.commit()
        assert recover_pending_action_mappings(db, now=NOW) == 0
        db.commit()
        assert db.get(TimeEvent, event_id).oracle_payroll_time_type is None


def test_invalid_or_inactive_current_catalogue_mapping_does_not_recover(db_factory):
    event_id = add_event(db_factory)
    with db_factory() as db:
        action = db.get(Action, 1)
        action.oracle_payroll_time_type = "Inactive type"
        db.commit()
        assert recover_pending_action_mappings(db, now=NOW) == 0
        db.commit()
        assert db.get(TimeEvent, event_id).oracle_payroll_time_type is None


def test_missing_perimeter_association_and_wrong_terminal_role_do_not_recover(db_factory):
    event_id = add_event(db_factory)
    with db_factory() as db:
        db.execute(terminal_actions.delete())
        db.commit()
        assert recover_pending_action_mappings(db, now=NOW) == 0
        terminal = db.get(Terminal, 1)
        terminal.terminal_role = "PERIMETER_EXIT"
        db.execute(insert(terminal_actions).values(terminal_id=1, action_id=1))
        db.commit()
        assert recover_pending_action_mappings(db, now=NOW) == 0
        db.commit()
        assert db.get(TimeEvent, event_id).oracle_payroll_time_type is None


def test_conflicting_action_code_and_other_readiness_errors_block_recovery(db_factory):
    event_id = add_event(db_factory)
    with db_factory() as db:
        db.get(Action, 1).code = "A different source action"
        db.commit()
        assert recover_pending_action_mappings(db, now=NOW) == 0
        db.get(Action, 1).code = "Synthetic EXIT"
        db.get(Action, 1).oracle_supplier_event = "HUT_TCD_SUPP1_IN_2"
        db.commit()
        assert recover_pending_action_mappings(db, now=NOW) == 0
        db.commit()
        assert db.get(TimeEvent, event_id).oracle_payroll_time_type is None
        assert db.scalars(select(OracleMappingRecoveryAudit)).all() == []


def test_rollback_discards_mapping_and_audit_together(db_factory):
    event_id = add_event(db_factory)
    with db_factory() as db:
        assert recover_pending_action_mappings(db, now=NOW) == 1
        db.rollback()
    with db_factory() as db:
        assert db.get(TimeEvent, event_id).oracle_payroll_time_type is None
        assert db.scalars(select(OracleMappingRecoveryAudit)).all() == []


def test_normal_worker_delivers_recovered_correlated_exit_via_mocked_oracle(db_factory, monkeypatch):
    from app import worker

    event_id = add_event(db_factory)
    with db_factory() as db:
        assert recover_pending_action_mappings(db, now=NOW) == 1
        db.commit()
    monkeypatch.setattr(worker.settings, "oracle_enabled", True)
    assert worker.claim_next_event() == event_id

    result = DeliveryResult(
        result=DeliveryStatus.SENT.value, retryable=False, ambiguous=False, status_code=201,
        duration_ms=1, request_payload={"requestNumber": f"BSS-{event_id}"},
        response_payload={"mock": True}, error_message=None, oracle_request_id="mock-request", oracle_event_id="mock-event",
    )

    class MockClient:
        endpoint = "https://oracle.invalid/mock"
        def send(self, event, db=None):
            assert event.correlation_id == "correlation-1"
            assert event.state_effect == "EXIT"
            assert event.oracle_payroll_time_type == "Approved type"
            return result

    from app.services.oracle_delivery import deliver_event
    deliver_event(event_id, MockClient(), session_factory=db_factory)
    with db_factory() as db:
        event = db.get(TimeEvent, event_id)
        assert event.delivery_status == "SENT"
        assert event.sent_at is not None
        assert event.oracle_request_id == "mock-request"
        assert db.scalars(select(OracleMappingRecoveryAudit).where(OracleMappingRecoveryAudit.event_id == event_id)).all()
        assert db.scalars(select(TransmissionAttempt).where(TransmissionAttempt.event_id == event_id)).all()


def test_postgresql_concurrent_recovery_locks_one_batch_and_is_idempotent():
    """Run against a disposable PostgreSQL DB via ORACLE_RECOVERY_TEST_DATABASE_URL."""
    url = os.getenv("ORACLE_RECOVERY_TEST_DATABASE_URL")
    if not url:
        pytest.skip("set ORACLE_RECOVERY_TEST_DATABASE_URL to run PostgreSQL concurrency coverage")
    schema = f"oracle_recovery_{uuid.uuid4().hex}"
    admin_engine = create_engine(url, pool_pre_ping=True)
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"}, pool_size=3)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        Base.metadata.create_all(engine)
        with factory() as db:
            db.add_all([
                Factory(id=1, code="PGF", name="Isolated test factory", timezone="UTC", active=True),
                OracleWorkArea(code="PGW", description="Test work area", active=True),
                OraclePayrollTimeType(code="PG approved", active=True, source_reference="isolated PostgreSQL concurrency test"),
            ])
            db.flush()
            db.add(OracleMachine(code="PGM", description="Test machine", work_area_code="PGW", active=True))
            db.flush()
            db.add(OracleCell(code="PGC", description="Test cell", machine_code="PGM", active=True))
            db.flush()
            action = Action(id=1, code="PG EXIT", label="PG EXIT", supplier_device_event="direct_exit",
                oracle_supplier_event="HUT_TCD_SUPP1_OUT_2", state_effect="EXIT", oracle_payroll_time_type="PG approved",
                oracle_attributes={}, display_order=1, requires_subaction=False, show_on_terminal=True, active=True)
            terminal = Terminal(id=1, factory_code="PGF", terminal_role="CELL", code="PGT", name="Test cell",
                external_device_id="PGD", identification_mode="RFID", reporter_id_type="BADGE", oracle_attributes={}, active=True)
            db.add_all([action, terminal]); db.flush()
            db.execute(insert(terminal_actions).values(terminal_id=terminal.id, action_id=action.id))
            db.add(TimeEvent(
                id="pg-concurrent-event", request_number="BSS-pg-concurrent-event", terminal_id=1, action_id=1,
                correlation_id="pg-correlation", terminal_code="PGT", device_id="PGD", action_code="PG EXIT",
                action_label="PG EXIT", supplier_device_event="direct_exit", oracle_supplier_event="HUT_TCD_SUPP1_OUT_2",
                state_effect="EXIT", reporter_id="test-badge", reporter_id_type="BADGE", identification_method="RFID",
                person_id="P100", oracle_reporter_id="P100", oracle_reporter_id_type="PERSON",
                event_datetime=NOW, event_timezone="Europe/Madrid", oracle_payroll_time_type=None,
                oracle_mapping_error="PayrollTimeType missing", oracle_attributes={}, workshop_code="local-W",
                subworkshop_code="local-S", project_line_code="local-P", oracle_work_area_code="PGW",
                oracle_machine_code="PGM", oracle_cell_code="PGC", delivery_status="PENDING", attempt_count=0,
                created_at=NOW,
            ))
            db.commit()

        first_recovered = threading.Event()
        release_first = threading.Event()
        outcomes = {}
        def first_worker():
            with factory() as db:
                outcomes["first"] = recover_pending_action_mappings(db, now=NOW)
                first_recovered.set()
                assert release_first.wait(timeout=10)
                db.commit()
        thread = threading.Thread(target=first_worker)
        thread.start()
        assert first_recovered.wait(timeout=10)
        with factory() as second:
            outcomes["second"] = recover_pending_action_mappings(second, now=NOW)
            second.commit()
        release_first.set()
        thread.join(timeout=10)
        assert not thread.is_alive()
        assert outcomes == {"first": 1, "second": 0}
        with factory() as db:
            assert recover_pending_action_mappings(db, now=NOW) == 0
            db.commit()
            event = db.get(TimeEvent, "pg-concurrent-event")
            audits = db.scalars(select(OracleMappingRecoveryAudit).where(
                OracleMappingRecoveryAudit.event_id == "pg-concurrent-event")).all()
            assert event.oracle_payroll_time_type == "PG approved"
            assert event.event_datetime.replace(tzinfo=timezone.utc) == NOW
            assert event.request_number == "BSS-pg-concurrent-event"
            assert event.correlation_id == "pg-correlation"
            assert len(audits) == 1 and audits[0].new_value == "PG approved"
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()
