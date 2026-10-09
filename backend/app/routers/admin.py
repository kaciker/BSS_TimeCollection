from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.enums import DeliveryStatus, StateEffect
from app.models.action import Action
from app.models.terminal import Terminal
from app.models.time_event import TimeEvent
from app.schemas.admin import ActionCreate, ActionRead, EventRead, TerminalActionsUpdate, TerminalCreate, TerminalRead, TerminalSettings, ActionSettings

from app.services.configuration_service import (
    check_device_id, check_supplier_event, commit_configuration, resolve_actions, validate_actions,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _terminal_read(terminal: Terminal) -> TerminalRead:
    return TerminalRead(
        code=terminal.code,
        name=terminal.name,
        external_device_id=terminal.external_device_id,
        identification_mode=terminal.identification_mode,
        active=terminal.active,
        action_codes=sorted(action.code for action in terminal.actions),
    )


@router.get("/terminals", response_model=list[TerminalRead])
def list_terminals(db: Session = Depends(get_db)):
    terminals = db.scalars(select(Terminal).order_by(Terminal.code)).unique().all()
    return [_terminal_read(item) for item in terminals]


@router.post("/terminals", response_model=TerminalRead, status_code=status.HTTP_201_CREATED)
def create_terminal(payload: TerminalCreate, db: Session = Depends(get_db)):
    if db.scalar(select(Terminal).where(Terminal.code == payload.code)):
        raise HTTPException(status_code=409, detail="Terminal code already exists")
    check_device_id(db, payload.external_device_id)
    actions = resolve_actions(db, payload.action_codes)
    if payload.active:
        validate_actions(actions, payload.code)
    terminal = Terminal(
        code=payload.code,
        name=payload.name,
        external_device_id=payload.external_device_id,
        identification_mode=payload.identification_mode.value,
        active=payload.active,
        actions=actions,
    )
    db.add(terminal)
    commit_configuration(db)
    db.refresh(terminal)
    return _terminal_read(terminal)


@router.put("/terminals/{terminal_code}", response_model=TerminalRead)
def update_terminal(terminal_code: str, payload: TerminalSettings, db: Session = Depends(get_db)):
    terminal = db.scalar(select(Terminal).where(Terminal.code == terminal_code))
    if terminal is None:
        raise HTTPException(404, "Terminal not found")
    check_device_id(db, payload.external_device_id, terminal)
    actions = resolve_actions(db, payload.action_codes)
    if payload.active:
        validate_actions(actions, terminal.code)
    terminal.name = payload.name
    terminal.external_device_id = payload.external_device_id
    terminal.identification_mode = payload.identification_mode.value
    terminal.active = payload.active
    terminal.actions = actions
    commit_configuration(db)
    db.refresh(terminal)
    return _terminal_read(terminal)


@router.put("/terminals/{terminal_code}/actions", response_model=TerminalRead)
def update_terminal_actions(terminal_code: str, payload: TerminalActionsUpdate, db: Session = Depends(get_db)):
    terminal = db.scalar(select(Terminal).where(Terminal.code == terminal_code))
    if terminal is None:
        raise HTTPException(status_code=404, detail="Terminal not found")
    actions = resolve_actions(db, payload.action_codes)
    if terminal.active:
        validate_actions(actions, terminal.code)
    terminal.actions = list(actions)
    commit_configuration(db)
    db.refresh(terminal)
    return _terminal_read(terminal)


@router.get("/actions", response_model=list[ActionRead])
def list_actions(db: Session = Depends(get_db)):
    actions = db.scalars(select(Action).order_by(Action.display_order, Action.code)).all()
    return [ActionRead(**{field: getattr(item, field) for field in ActionRead.model_fields}) for item in actions]


@router.post("/actions", response_model=ActionRead, status_code=status.HTTP_201_CREATED)
def create_action(payload: ActionCreate, db: Session = Depends(get_db)):
    if db.scalar(select(Action).where(Action.code == payload.code)):
        raise HTTPException(status_code=409, detail="Action code already exists")
    check_supplier_event(db, payload.supplier_device_event)
    action = Action(
        code=payload.code,
        label=payload.label,
        supplier_device_event=payload.supplier_device_event,
        state_effect=payload.state_effect.value,
        reporter_id_type=payload.reporter_id_type,
        oracle_attributes=payload.oracle_attributes,
        display_order=payload.display_order,
        active=payload.active,
    )
    db.add(action)
    commit_configuration(db)
    db.refresh(action)
    return ActionRead(**{field: getattr(action, field) for field in ActionRead.model_fields})


@router.put("/actions/{action_code}", response_model=ActionRead)
def update_action(action_code: str, payload: ActionSettings, db: Session = Depends(get_db)):
    action = db.scalar(select(Action).where(Action.code == action_code))
    if action is None:
        raise HTTPException(404, "Action not found")
    check_supplier_event(db, payload.supplier_device_event, action)
    # Validate all assigned active terminals before committing the new effect/status.
    # Historical events retain their snapshots; only future captures use these values.
    for field, value in payload.model_dump().items():
        setattr(action, field, value.value if field == "state_effect" else value)
    try:
        for terminal in action.terminals:
            if terminal.active:
                validate_actions(terminal.actions, terminal.code)
    except HTTPException:
        db.rollback()
        raise
    commit_configuration(db)
    db.refresh(action)
    return ActionRead(**{field: getattr(action, field) for field in ActionRead.model_fields})


@router.get("/events", response_model=list[EventRead])
def list_events(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    events = db.scalars(select(TimeEvent).order_by(TimeEvent.created_at.desc()).limit(limit)).all()
    return [EventRead(**{field: getattr(item, field) for field in EventRead.model_fields}) for item in events]


@router.post("/events/{event_id}/retry", response_model=EventRead)
def retry_event(event_id: str, db: Session = Depends(get_db)):
    event = db.get(TimeEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.delivery_status == DeliveryStatus.SENT.value:
        raise HTTPException(status_code=409, detail="A sent event cannot be replayed")
    event.delivery_status = DeliveryStatus.PENDING.value
    event.next_attempt_at = None
    db.commit()
    db.refresh(event)
    return EventRead(**{field: getattr(event, field) for field in EventRead.model_fields})
