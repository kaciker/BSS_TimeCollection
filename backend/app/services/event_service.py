from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.enums import IdentificationMethod, IdentificationMode, StateEffect, WorkerState
from app.models.action import Action
from app.models.terminal import Terminal
from app.models.time_event import TimeEvent
from app.schemas.terminal import CapturedEvent, ScanResponse, TerminalAction
from app.services.state_service import derive_worker_state


def _get_terminal(db: Session, terminal_code: str) -> Terminal:
    terminal = db.scalar(select(Terminal).where(Terminal.code == terminal_code))
    if terminal is None or not terminal.active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terminal not found or inactive")
    return terminal


def _validate_method(terminal: Terminal, method: IdentificationMethod) -> None:
    allowed = terminal.identification_mode
    if allowed != IdentificationMode.BOTH.value and allowed != method.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Identification method is not enabled on this terminal")


def _active_actions(terminal: Terminal, effect: StateEffect) -> list[Action]:
    return sorted(
        [action for action in terminal.actions if action.active and action.state_effect == effect.value],
        key=lambda action: (action.display_order, action.id),
    )


def _create_event(db: Session, terminal: Terminal, action: Action, reporter_id: str, method: IdentificationMethod) -> TimeEvent:
    event_id = str(uuid4())
    event_time = datetime.now(ZoneInfo(settings.event_timezone))
    event = TimeEvent(
        id=event_id,
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
        reporter_id_type=action.reporter_id_type,
        identification_method=method.value,
        event_datetime=event_time,
        event_timezone=settings.event_timezone,
        oracle_attributes=action.oracle_attributes or {},
        delivery_status="PENDING",
    )
    db.add(event)
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
    terminal = _get_terminal(db, terminal_code)
    _validate_method(terminal, method)
    current_state = derive_worker_state(db, reporter_id)

    if current_state == WorkerState.OUTSIDE:
        entry_actions = _active_actions(terminal, StateEffect.ENTER)
        if len(entry_actions) != 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Terminal must have exactly one active ENTER action for automatic entry",
            )
        event = _create_event(db, terminal, entry_actions[0], reporter_id, method)
        return ScanResponse(flow="ENTRY_RECORDED", worker_state=WorkerState.INSIDE.value, event=_event_response(event))

    exit_actions = _active_actions(terminal, StateEffect.EXIT)
    if not exit_actions:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Terminal has no active EXIT actions")
    return ScanResponse(
        flow="EXIT_REQUIRED",
        worker_state=WorkerState.INSIDE.value,
        actions=[TerminalAction(code=action.code, label=action.label) for action in exit_actions],
    )


def record_exit(db: Session, terminal_code: str, reporter_id: str, method: IdentificationMethod, action_code: str) -> ScanResponse:
    terminal = _get_terminal(db, terminal_code)
    _validate_method(terminal, method)
    if derive_worker_state(db, reporter_id) != WorkerState.INSIDE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Worker is not currently inside according to local TCD events")

    action = next((item for item in _active_actions(terminal, StateEffect.EXIT) if item.code == action_code), None)
    if action is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Exit action is not enabled on this terminal")

    event = _create_event(db, terminal, action, reporter_id, method)
    return ScanResponse(flow="EXIT_RECORDED", worker_state=WorkerState.OUTSIDE.value, event=_event_response(event))
