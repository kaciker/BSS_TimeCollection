from datetime import datetime
from hashlib import sha256
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.enums import IdentificationMethod, IdentificationMode, StateEffect, WorkerState
from app.models.action import Action
from app.models.terminal import Terminal
from app.models.time_event import TimeEvent
from app.schemas.terminal import CapturedEvent, ScanResponse, TerminalAction
from app.services.state_service import derive_worker_state
from app.services.exit_policy import check_exit_policy


def _lock_badge(db: Session, reporter_id: str) -> None:
    # Serialize state evaluation and capture across all PostgreSQL terminals.
    # A transaction advisory lock also covers a badge with no existing events.
    if db.get_bind().dialect.name == "postgresql":
        key = int.from_bytes(sha256(reporter_id.encode()).digest()[:8], "big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def _get_terminal(db: Session, terminal_code: str) -> Terminal:
    terminal = db.scalar(select(Terminal).where(Terminal.code == terminal_code))
    if terminal is None or not terminal.active or terminal.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terminal not found or inactive")
    return terminal


def _validate_method(terminal: Terminal, method: IdentificationMethod) -> None:
    allowed = terminal.identification_mode
    if allowed != IdentificationMode.BOTH.value and allowed != method.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Identification method is not enabled on this terminal")


def _active_actions(terminal: Terminal, effect: StateEffect) -> list[Action]:
    return sorted(
        [action for action in terminal.actions if action.active and action.show_on_terminal and action.state_effect == effect.value],
        key=lambda action: (action.display_order, action.id),
    )


def _terminal_action(action: Action) -> TerminalAction:
    return TerminalAction(code=action.code, label=action.label, has_subactions=action.requires_subaction, visual_key=action.visual_key)


def _create_event(db: Session, terminal: Terminal, action: Action, reporter_id: str, method: IdentificationMethod, *, commit: bool = True, event_time: datetime | None = None, correlation_id: str | None = None, snapshot: TimeEvent | None = None) -> TimeEvent:
    if terminal.terminal_role != "CELL":
        raise HTTPException(409, "Perimeter terminals cannot create cell time events")
    event_id = str(uuid4())
    event_time = event_time or datetime.now(ZoneInfo(settings.event_timezone))
    # work_cell is a local exit-policy attribute, not part of the Oracle TCD context.
    oracle_attributes = {key: value for key, value in (terminal.oracle_attributes or {}).items() if key != "work_cell"}
    oracle_attributes.update({key: value for key, value in (action.oracle_attributes or {}).items() if key != "work_cell"})
    structure = terminal.project_line
    branch = structure.subworkshop if structure else None
    workshop = branch.workshop if branch else None
    if snapshot is None and structure and (not structure.active or not branch.active or not workshop.active):
        raise HTTPException(status_code=409, detail="Assigned operational structure is inactive")
    event = TimeEvent(
        workshop_code=workshop.code if workshop else None,
        workshop_description=workshop.description if workshop else None,
        subworkshop_code=branch.code if branch else None,
        subworkshop_description=branch.description if branch else None,
        project_line_code=structure.code if structure else None,
        project_line_description=structure.description if structure else None,
        id=event_id,
        correlation_id=correlation_id,
        request_number=f"BSS-{terminal.code}-{event_id}",
        terminal_id=terminal.id,
        action_id=action.id,
        terminal_code=terminal.code,
        device_id=terminal.external_device_id,
        action_code=action.code,
        action_label=action.label,
        supplier_device_event=action.supplier_device_event,
        state_effect=action.state_effect,
        reporter_id=reporter_id,
        reporter_id_type=settings.oracle_reporter_id_type,
        identification_method=method.value,
        event_datetime=event_time,
        event_timezone=settings.event_timezone,
        oracle_attributes=oracle_attributes,
        delivery_status="PENDING",
    )
    if snapshot is not None:
        for field in ("terminal_code", "device_id", "workshop_code", "workshop_description", "subworkshop_code", "subworkshop_description", "project_line_code", "project_line_description"):
            setattr(event, field, getattr(snapshot, field))
        event.oracle_attributes = {**(snapshot.oracle_attributes or {}), **{k: v for k, v in (action.oracle_attributes or {}).items() if k != "work_cell"}}
    db.add(event)
    if commit:
        db.commit()
        db.refresh(event)
    return event


def _event_response(event: TimeEvent) -> CapturedEvent:
    return CapturedEvent(
        id=event.id,
        action_code=event.action_code,
        action_label=event.action_label,
        event_datetime=event.event_datetime,
        delivery_status=event.delivery_status,
    )


def scan(db: Session, terminal_code: str, reporter_id: str, method: IdentificationMethod) -> ScanResponse:
    _lock_badge(db, reporter_id)
    terminal = _get_terminal(db, terminal_code)
    _validate_method(terminal, method)
    from datetime import timezone
    from app.services.perimeter_service import settings_for, is_inside, is_duplicate, remember_read, perimeter_scan, check_badge_source
    if terminal.terminal_role != "CELL":
        return ScanResponse(**perimeter_scan(db, terminal, reporter_id, method))
    config = settings_for(db, terminal.factory_code)
    now = datetime.now(timezone.utc)
    current_state = derive_worker_state(db, reporter_id, terminal.factory_code)
    if current_state == WorkerState.OUTSIDE and config.enabled:
        check_badge_source(config, reporter_id)
        if config.badge_source != "EXTERNAL" and not is_inside(db, terminal.factory_code, reporter_id):
            raise HTTPException(409, "Badge has not entered the factory perimeter")
    if is_duplicate(db, config, terminal, reporter_id, now):
        return ScanResponse(flow="DUPLICATE_IGNORED", worker_state=current_state.value)

    if current_state == WorkerState.OUTSIDE:
        entry_actions = _active_actions(terminal, StateEffect.ENTER)
        if len(entry_actions) != 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Terminal must have exactly one active ENTER action for automatic entry",
            )
        remember_read(db, terminal, reporter_id, now)
        event = _create_event(db, terminal, entry_actions[0], reporter_id, method)
        return ScanResponse(flow="ENTRY_RECORDED", worker_state=WorkerState.INSIDE.value, event=_event_response(event))

    check_exit_policy(db, terminal, reporter_id)
    enabled_exits = _active_actions(terminal, StateEffect.EXIT)
    enabled_ids = {action.id for action in enabled_exits}
    exit_actions = [action for action in enabled_exits if action.parent_action_id is None or action.parent_action_id not in enabled_ids]
    if not exit_actions:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Terminal has no active EXIT actions")
    return ScanResponse(
        flow="EXIT_REQUIRED",
        worker_state=WorkerState.INSIDE.value,
        actions=[_terminal_action(action) for action in exit_actions],
    )


def record_exit(db: Session, terminal_code: str, reporter_id: str, method: IdentificationMethod, action_code: str) -> ScanResponse:
    _lock_badge(db, reporter_id)
    terminal = _get_terminal(db, terminal_code)
    _validate_method(terminal, method)
    if terminal.terminal_role != "CELL":
        raise HTTPException(409, "Perimeter terminals do not accept cell exit actions")
    from datetime import timezone
    from app.services.perimeter_service import settings_for, is_duplicate
    current_state = derive_worker_state(db, reporter_id, terminal.factory_code)
    if current_state != WorkerState.INSIDE and is_duplicate(db, settings_for(db, terminal.factory_code), terminal, reporter_id, datetime.now(timezone.utc)):
        return ScanResponse(flow="DUPLICATE_IGNORED", worker_state=current_state.value)
    if current_state != WorkerState.INSIDE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Worker is not currently inside according to local TCD events")

    check_exit_policy(db, terminal, reporter_id)
    exit_actions = _active_actions(terminal, StateEffect.EXIT)
    action = next((item for item in exit_actions if item.code == action_code), None)
    if action is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Exit action is not enabled on this terminal")

    if action.requires_subaction:
        children = sorted(
            [item for item in exit_actions if item.parent_action_id == action.id],
            key=lambda item: (item.display_order, item.id),
        )
        if not children:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Selected exit action has no active sub-actions")
        return ScanResponse(
            flow="SUBACTION_REQUIRED",
            worker_state=WorkerState.INSIDE.value,
            actions=[_terminal_action(item) for item in children],
        )

    if action.parent_action_id is not None:
        parent = next((item for item in exit_actions if item.id == action.parent_action_id), None)
        if parent is not None and not parent.requires_subaction:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sub-action parent is not enabled on this terminal")

    from datetime import timezone
    from app.services.perimeter_service import remember_read
    remember_read(db, terminal, reporter_id, datetime.now(timezone.utc))
    event = _create_event(db, terminal, action, reporter_id, method)
    return ScanResponse(flow="EXIT_RECORDED", worker_state=WorkerState.OUTSIDE.value, event=_event_response(event))
