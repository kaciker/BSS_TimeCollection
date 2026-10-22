from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session

from app.core.config import settings
from app.db.session import get_db
from app.domain.enums import DeliveryStatus
from app.models.action import Action
from app.models.terminal import Terminal
from app.models.structure import ProjectLine
from app.models.terminal_pairing_request import TerminalPairingRequest
from app.models.time_event import TimeEvent
from app.schemas.admin import (
    ActionCreate,
    ActionRead,
    ActionSettings,
    EventRead,
    TerminalActionsUpdate,
    TerminalCreate,
    TerminalPairingApproval,
    TerminalProvisioningRead,
    TerminalRead,
    TerminalSettings,
)
from app.services.configuration_service import (
    check_device_id,
    check_supplier_event,
    commit_configuration,
    resolve_actions,
    resolve_parent_action,
    validate_action_hierarchy,
    validate_actions,
)
from app.services.exit_policy import get_mode, save_mode, policies
from app.services.terminal_cloning_service import clone_terminal
from app.services.terminal_code_service import allocate_terminal_code
from app.services.terminal_identity_service import issue_activation_token
from app.services.terminal_pairing_service import approve_pairing_request

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])



def _resolve_structure(db: Session, leaf_id: int | None, workshop_id: int | None, subworkshop_id: int | None, *, required: bool) -> ProjectLine | None:
    if leaf_id is None:
        if required or workshop_id is not None or subworkshop_id is not None:
            raise HTTPException(422, "Select a complete Workshop / Subworkshop / Project / Line path")
        return None
    leaf = db.get(ProjectLine, leaf_id)
    if leaf is None or not leaf.active or not leaf.subworkshop.active or not leaf.subworkshop.workshop.active:
        raise HTTPException(422, "Project / Line path does not exist or is inactive")
    if subworkshop_id is not None and subworkshop_id != leaf.subworkshop_id:
        raise HTTPException(422, "Subworkshop does not match Project / Line")
    if workshop_id is not None and workshop_id != leaf.subworkshop.workshop_id:
        raise HTTPException(422, "Workshop does not match Project / Line")
    return leaf


def _commit_terminal_settings(db: Session, terminal: Terminal, mode: str | None) -> None:
    try:
        if mode is not None:
            db.flush()
            save_mode(db, terminal.id, mode, commit=False)
        commit_configuration(db)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Code, device ID or supplier event already exists")


def _terminal_read(terminal: Terminal, activation_token: str | None = None) -> TerminalRead:
    db = object_session(terminal)
    override = db.execute(select(policies.c.mode).where(policies.c.terminal_id == terminal.id)).scalar_one_or_none()
    return TerminalRead(
        factory_code=terminal.factory_code,
        terminal_role=terminal.terminal_role,
        code=terminal.code,
        name=terminal.name,
        external_device_id=terminal.external_device_id,
        identification_mode=terminal.identification_mode,
        exit_menu_timeout_seconds=terminal.exit_menu_timeout_seconds,
        reporter_id_type=settings.oracle_reporter_id_type,
        oracle_attributes=terminal.oracle_attributes or {},
        active=terminal.active,
        action_codes=sorted(action.code for action in terminal.actions),
        provisioned=bool(terminal.session_token_hash),
        activation_pending=bool(terminal.activation_token_hash),
        activation_token=activation_token,
        project_line_id=terminal.project_line_id,
        subworkshop_id=terminal.project_line.subworkshop_id if terminal.project_line else None,
        workshop_id=terminal.project_line.subworkshop.workshop_id if terminal.project_line else None,
        structure_path=" / ".join([terminal.project_line.subworkshop.workshop.code, terminal.project_line.subworkshop.code, terminal.project_line.code]) if terminal.project_line else None,
        exit_policy_mode=override or "INHERIT",
        effective_exit_policy_mode=get_mode(db, terminal.id),
        global_exit_policy_mode=get_mode(db, None),
    )


def _action_read(action: Action) -> ActionRead:
    return ActionRead(
        code=action.code,
        label=action.label,
        supplier_device_event=action.supplier_device_event,
        state_effect=action.state_effect,
        oracle_attributes=action.oracle_attributes or {},
        display_order=action.display_order,
        requires_subaction=action.requires_subaction,
        visual_key=action.visual_key,
        show_on_terminal=action.show_on_terminal,
        parent_action_code=action.parent_action.code if action.parent_action else None,
        subaction_codes=sorted(child.code for child in action.subactions),
        active=action.active,
    )


@router.get("/integration-settings")
def integration_settings():
    return {
        "oracle_enabled": settings.oracle_enabled,
        "oracle_source_id": settings.oracle_source_id,
        "reporter_id_type": settings.oracle_reporter_id_type,
    }


@router.get("/terminals", response_model=list[TerminalRead])
def list_terminals(db: Session = Depends(get_db)):
    terminals = db.scalars(select(Terminal).where(Terminal.deleted_at.is_(None)).order_by(Terminal.code)).unique().all()
    return [_terminal_read(item) for item in terminals]


@router.post("/terminals", response_model=TerminalRead, status_code=status.HTTP_201_CREATED)
def create_terminal(payload: TerminalCreate, db: Session = Depends(get_db)):
    terminal_code = payload.code or allocate_terminal_code(db)
    if db.scalar(select(Terminal).where(Terminal.code == terminal_code)):
        raise HTTPException(status_code=409, detail="Terminal code already exists")
    device_id = payload.external_device_id
    if payload.perimeter_only:
        device_id = device_id or (terminal_code if len(terminal_code) <= 40 else "GATE-" + uuid4().hex)
    if not device_id:
        raise HTTPException(422, "Oracle device ID is required for a cell terminal")
    check_device_id(db, device_id)
    actions = [] if payload.perimeter_only else resolve_actions(db, payload.action_codes)
    if payload.active:
        validate_actions(actions, terminal_code, "PERIMETER_BOTH" if payload.perimeter_only else "CELL")
    leaf = None if payload.perimeter_only else _resolve_structure(db, payload.project_line_id, payload.workshop_id, payload.subworkshop_id, required=True)
    terminal = Terminal(
        project_line_id=leaf.id if leaf else None,
        code=terminal_code,
        name=payload.name,
        external_device_id=device_id,
        terminal_role="PERIMETER_BOTH" if payload.perimeter_only else "CELL",
        identification_mode=payload.identification_mode.value,
        exit_menu_timeout_seconds=payload.exit_menu_timeout_seconds if payload.exit_menu_timeout_seconds is not None else 5,
        reporter_id_type=settings.oracle_reporter_id_type,
        oracle_attributes={} if payload.perimeter_only else payload.oracle_attributes,
        active=payload.active,
        actions=actions,
    )
    activation_token = issue_activation_token(terminal)
    db.add(terminal)
    _commit_terminal_settings(db, terminal, "DISABLED" if terminal.terminal_role != "CELL" else payload.exit_policy_mode)
    db.refresh(terminal)
    return _terminal_read(terminal, activation_token)


@router.post("/terminals/{terminal_code}/clone", response_model=TerminalRead, status_code=status.HTTP_201_CREATED)
def clone_terminal_configuration(terminal_code: str, db: Session = Depends(get_db)):
    return _terminal_read(clone_terminal(db, terminal_code))


@router.put("/terminals/{terminal_code}", response_model=TerminalRead)
def update_terminal(terminal_code: str, payload: TerminalSettings, db: Session = Depends(get_db)):
    terminal = db.scalar(select(Terminal).where(Terminal.code == termin…308 tokens truncated…oad.identification_mode.value
    if payload.exit_menu_timeout_seconds is not None:
        terminal.exit_menu_timeout_seconds = payload.exit_menu_timeout_seconds
    terminal.reporter_id_type = settings.oracle_reporter_id_type
    terminal.oracle_attributes = {} if perimeter else payload.oracle_attributes
    terminal.active = payload.active
    terminal.actions = actions
    _commit_terminal_settings(db, terminal, "DISABLED" if terminal.terminal_role != "CELL" else payload.exit_policy_mode)
    db.refresh(terminal)
    return _terminal_read(terminal)


@router.delete("/terminals/{terminal_code}")
def delete_terminal(terminal_code: str, db: Session = Depends(get_db)):
    terminal = db.scalar(select(Terminal).where(Terminal.code == terminal_code, Terminal.deleted_at.is_(None)).with_for_update())
    if terminal is None:
        raise HTTPException(404, "Terminal not found")
    terminal.active = False
    terminal.deleted_at = datetime.now(timezone.utc)
    terminal.activation_token_hash = None
    terminal.session_token_hash = None
    # Keep approved requests for audit; polling checks the removed terminal.
    for pairing in db.scalars(select(TerminalPairingRequest).where(
        TerminalPairingRequest.terminal_id == terminal.id,
        TerminalPairingRequest.status == "APPROVED",
    )):
        pairing.status = "CANCELLED"
    commit_configuration(db)
    return {"detail": f"Terminal {terminal_code} removed"}


@router.post("/terminals/{terminal_code}/provision", response_model=TerminalProvisioningRead)
def provision_terminal(terminal_code: str, db: Session = Depends(get_db)):
    terminal = db.scalar(select(Terminal).where(Terminal.code == terminal_code, Terminal.deleted_at.is_(None)).with_for_update())
    if terminal is None:
        raise HTTPException(404, "Terminal not found")
    token = issue_activation_token(terminal)
    commit_configuration(db)
    return TerminalProvisioningRead(code=terminal.code, activation_token=token)


@router.post("/terminals/{terminal_code}/pair", response_model=TerminalRead)
def pair_terminal_browser(terminal_code: str, payload: TerminalPairingApproval, db: Session = Depends(get_db)):
    terminal = db.scalar(select(Terminal).where(Terminal.code == terminal_code, Terminal.deleted_at.is_(None)).with_for_update())
    if terminal is None:
        raise HTTPException(404, "Terminal not found")
    approve_pairing_request(db, terminal, payload.pairing_code)
    db.refresh(terminal)
    return _terminal_read(terminal)


@router.put("/terminals/{terminal_code}/actions", response_model=TerminalRead)
def update_terminal_actions(terminal_code: str, payload: TerminalActionsUpdate, db: Session = Depends(get_db)):
    terminal = db.scalar(select(Terminal).where(Terminal.code == terminal_code, Terminal.deleted_at.is_(None)))
    if terminal is None:
        raise HTTPException(status_code=404, detail="Terminal not found")
    actions = resolve_actions(db, payload.action_codes)
    if terminal.active:
        validate_actions(actions, terminal.code, terminal.terminal_role)
    terminal.actions = list(actions)
    commit_configuration(db)
    db.refresh(terminal)
    return _terminal_read(terminal)


@router.get("/actions", response_model=list[ActionRead])
def list_actions(db: Session = Depends(get_db)):
    actions = db.scalars(select(Action).order_by(Action.display_order, Action.code)).unique().all()
    return [_action_read(item) for item in actions]


@router.post("/actions", response_model=ActionRead, status_code=status.HTTP_201_CREATED)
def create_action(payload: ActionCreate, db: Session = Depends(get_db)):
    if db.scalar(select(Action).where(Action.code == payload.code)):
        raise HTTPException(status_code=409, detail="Action code already exists")
    check_supplier_event(db, payload.supplier_device_event)
    parent = resolve_parent_action(db, payload.parent_action_code)
    action = Action(
        code=payload.code,
        label=payload.label,
        supplier_device_event=payload.supplier_device_event,
        state_effect=payload.state_effect.value,
        reporter_id_type="BADGE",
        oracle_attributes=payload.oracle_attributes,
        display_order=payload.display_order,
        requires_subaction=payload.requires_subaction,
        visual_key=payload.visual_key,
        show_on_terminal=payload.show_on_terminal,
        parent_action=parent,
        active=payload.active,
    )
    validate_action_hierarchy(action, parent)
    db.add(action)
    commit_configuration(db)
    db.refresh(action)
    return _action_read(action)


@router.put("/actions/{action_code}", response_model=ActionRead)
def update_action(action_code: str, payload: ActionSettings, db: Session = Depends(get_db)):
    action = db.scalar(select(Action).where(Action.code == action_code))
    if action is None:
        raise HTTPException(404, "Action not found")
    check_supplier_event(db, payload.supplier_device_event, action)
    parent = resolve_parent_action(db, payload.parent_action_code, action)
    action.label = payload.label
    action.supplier_device_event = payload.supplier_device_event
    action.state_effect = payload.state_effect.value
    action.oracle_attributes = payload.oracle_attributes
    action.display_order = payload.display_order
    action.requires_subaction = payload.requires_subaction
    action.visual_key = payload.visual_key
    action.show_on_terminal = payload.show_on_terminal
    action.parent_action = parent
    action.active = payload.active
    try:
        validate_action_hierarchy(action, parent)
        affected = {terminal.id: terminal for terminal in action.terminals}
        if parent:
            affected.update({terminal.id: terminal for terminal in parent.terminals})
        for child in action.subactions:
            affected.update({terminal.id: terminal for terminal in child.terminals})
        for terminal in affected.values():
            if terminal.active:
                validate_actions(terminal.actions, terminal.code, terminal.terminal_role)
    except HTTPException:
        db.rollback()
        raise
    commit_configuration(db)
    db.refresh(action)
    return _action_read(action)


@router.get("/events", response_model=list[EventRead])
def list_events(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    events = db.scalars(select(TimeEvent).order_by(TimeEvent.created_at.desc()).limit(limit)).all()
    return [EventRead(**{field: getattr(item, field) for field in EventRead.model_fields}) for item in events]


@router.post("/events/{event_id}/retry", response_model=EventRead)
def retry_event(event_id: str, db: Session = Depends(get_db)):
    event = db.get(TimeEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.delivery_status == DeliveryStatus.UNKNOWN.value:
        raise HTTPException(status_code=409, detail="UNKNOWN delivery requires reconciliation before any resend")
    if event.delivery_status == DeliveryStatus.REJECTED.value:
        raise HTTPException(status_code=409, detail="REJECTED delivery cannot be replayed blindly; correct the mapping or source data first")
    if event.delivery_status == DeliveryStatus.SENT.value:
        raise HTTPException(status_code=409, detail="A sent event cannot be replayed")
    if event.delivery_status == DeliveryStatus.SENDING.value:
        raise HTTPException(status_code=409, detail="An event currently being sent cannot be replayed")
    if event.delivery_status == DeliveryStatus.PENDING.value:
        raise HTTPException(status_code=409, detail="This event is already queued for delivery")
    event.delivery_status = DeliveryStatus.PENDING.value
    event.next_attempt_at = None
    db.commit()
    db.refresh(event)
    return EventRead(**{field: getattr(event, field) for field in EventRead.model_fields})
