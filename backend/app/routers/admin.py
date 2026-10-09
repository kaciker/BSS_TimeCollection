from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.enums import DeliveryStatus, StateEffect
from app.models.action import Action
from app.models.terminal import Terminal
from app.models.time_event import TimeEvent
from app.schemas.admin import ActionCreate, ActionRead, EventRead, TerminalActionsUpdate, TerminalCreate, TerminalRead

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
    terminal = Terminal(
        code=payload.code,
        name=payload.name,
        external_device_id=payload.external_device_id,
        identification_mode=payload.identification_mode.value,
    )
    db.add(terminal)
    db.commit()
    db.refresh(terminal)
    return _terminal_read(terminal)


@router.put("/terminals/{terminal_code}/actions", response_model=TerminalRead)
def update_terminal_actions(terminal_code: str, payload: TerminalActionsUpdate, db: Session = Depends(get_db)):
    terminal = db.scalar(select(Terminal).where(Terminal.code == terminal_code))
    if terminal is None:
        raise HTTPException(status_code=404, detail="Terminal not found")
    actions = db.scalars(select(Action).where(Action.code.in_(payload.action_codes))).all() if payload.action_codes else []
    if len(actions) != len(set(payload.action_codes)):
        raise HTTPException(status_code=400, detail="One or more action codes do not exist")
    if len([item for item in actions if item.active and item.state_effect == StateEffect.ENTER.value]) != 1:
        raise HTTPException(status_code=400, detail="A terminal must have exactly one active ENTER action")
    terminal.actions = list(actions)
    db.commit()
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
    action = Action(
        code=payload.code,
        label=payload.label,
        supplier_device_event=payload.supplier_device_event,
        state_effect=payload.state_effect.value,
        reporter_id_type=payload.reporter_id_type,
        oracle_attributes=payload.oracle_attributes,
        display_order=payload.display_order,
    )
    db.add(action)
    db.commit()
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
