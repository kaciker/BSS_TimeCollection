"""Safely restore missing action mappings on never-attempted pending events."""
from datetime import datetime, timezone

from sqlalchemy import exists, or_, select

from app.domain.enums import DeliveryStatus
from app.models.action import Action
from app.models.oracle_catalogue import OraclePayrollTimeType
from app.models.oracle_mapping_recovery import OracleMappingRecoveryAudit
from app.models.terminal import Terminal, terminal_actions
from app.models.time_event import TimeEvent
from app.models.transmission_attempt import TransmissionAttempt
from app.services.oracle_readiness import SUPPLIER_EVENT_BY_DIRECTION, oracle_readiness_errors

BATCH_SIZE = 64
RECOVERY_REASON = (
    "Restored a null Oracle mapping from the event's linked, active source action after "
    "the action configuration became catalogue-valid; no delivery attempt had occurred."
)


def recover_pending_action_mappings(db, *, limit: int = BATCH_SIZE, now: datetime | None = None) -> int:
    """Repair a small locked batch; caller owns and commits the transaction."""
    now = now or datetime.now(timezone.utc)
    has_attempt = exists(select(TransmissionAttempt.id).where(TransmissionAttempt.event_id == TimeEvent.id))
    linked_action = exists(
        select(terminal_actions.c.action_id).where(
            terminal_actions.c.terminal_id == TimeEvent.terminal_id,
            terminal_actions.c.action_id == TimeEvent.action_id,
        )
    )
    statement = (
        select(TimeEvent)
        .join(Terminal, Terminal.id == TimeEvent.terminal_id)
        .join(Action, Action.id == TimeEvent.action_id)
        .where(TimeEvent.delivery_status == DeliveryStatus.PENDING.value)
        .where(TimeEvent.attempt_count == 0)
        .where(TimeEvent.last_attempt_at.is_(None))
        .where(TimeEvent.sent_at.is_(None))
        .where(TimeEvent.oracle_request_id.is_(None))
        .where(TimeEvent.oracle_event_id.is_(None))
        .where(~has_attempt)
        .where(linked_action)
        .where(Terminal.terminal_role == "CELL")
        .where(Action.active.is_(True))
        # The action must have been edited after this captured event; otherwise
        # the live configuration does not establish a later correction.
        .where(Action.updated_at > TimeEvent.created_at)
        .where(Action.state_effect == TimeEvent.state_effect)
        .where(or_(TimeEvent.oracle_payroll_time_type.is_(None), TimeEvent.oracle_supplier_event.is_(None)))
        .order_by(TimeEvent.created_at, TimeEvent.id)
        .with_for_update(of=(TimeEvent, Action), skip_locked=True)
        .limit(max(1, min(limit, BATCH_SIZE)))
    )
    recovered = 0
    for event in db.scalars(statement):
        action = db.get(Action, event.action_id)
        terminal = db.get(Terminal, event.terminal_id)
        if (
            action is None or terminal is None or not action.active or terminal.terminal_role != "CELL"
            or action.code != event.action_code or action.state_effect != event.state_effect
            or terminal.code != event.terminal_code
        ):
            continue
        if db.scalar(select(OracleMappingRecoveryAudit.id).where(OracleMappingRecoveryAudit.event_id == event.id).limit(1)):
            continue

        prior_errors = oracle_readiness_errors(event, db)
        allowed_errors: set[str] = set()
        repairs: list[tuple[str, str | None, str, str]] = []

        if event.oracle_payroll_time_type is None:
            code = action.oracle_payroll_time_type
            catalogue_row = db.get(OraclePayrollTimeType, code) if code else None
            if catalogue_row is not None and catalogue_row.active and code and code.strip():
                allowed_errors.add("PayrollTimeType is missing or not in the HR-Path catalogue")
                repairs.append(("oracle_payroll_time_type", None, code,
                                catalogue_row.source_reference or f"actions.{action.id}.oracle_payroll_time_type"))

        expected_supplier = SUPPLIER_EVENT_BY_DIRECTION.get(event.state_effect)
        if event.oracle_supplier_event is None and expected_supplier and action.oracle_supplier_event == expected_supplier:
            allowed_errors.add("Oracle supplier event/direction mapping is invalid")
            repairs.append(("oracle_supplier_event", None, expected_supplier,
                            f"actions.{action.id}.oracle_supplier_event/{event.state_effect}"))
        elif action.oracle_supplier_event != expected_supplier:
            # A linked action with a conflicting direction is not a safe
            # source for recovering any other field on the event.
            continue

        if not repairs or any(error not in allowed_errors for error in prior_errors):
            continue

        previous_values = {field_name: previous for field_name, previous, _value, _ref in repairs}
        for field_name, _previous_value, new_value, _reference in repairs:
            setattr(event, field_name, new_value)
        # A repair is committed only when every Oracle identity, structure,
        # hierarchy and action-direction check now passes.
        if oracle_readiness_errors(event, db):
            for field_name, previous_value in previous_values.items():
                setattr(event, field_name, previous_value)
            continue
        for field_name, previous_value, new_value, reference in repairs:
            db.add(OracleMappingRecoveryAudit(
                event_id=event.id,
                field_name=field_name,
                previous_value=previous_value,
                new_value=new_value,
                source_action_id=action.id,
                source_action_code=action.code,
                mapping_reference=reference,
                recovered_at=now,
                recovery_reason=RECOVERY_REASON,
            ))
        event.oracle_mapping_error = None
        recovered += 1
    return recovered
