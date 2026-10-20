from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.action import Action
from app.models.terminal import Terminal


def resolve_actions(db: Session, codes: list[str]) -> list[Action]:
    rows = list(db.scalars(select(Action).where(Action.code.in_(codes))).all()) if codes else []
    if len(rows) != len(set(codes)):
        raise HTTPException(400, "One or more action codes do not exist")
    return rows


def resolve_parent_action(db: Session, parent_code: str | None, action: Action | None = None) -> Action | None:
    if not parent_code:
        return None
    parent = db.scalar(select(Action).where(Action.code == parent_code))
    if parent is None:
        raise HTTPException(400, "Parent action does not exist")
    if action is not None and parent.id == action.id:
        raise HTTPException(400, "An action cannot be its own parent")
    if parent.state_effect != "EXIT":
        raise HTTPException(409, "Only EXIT actions can own sub-actions")
    if parent.parent_action_id is not None:
        raise HTTPException(409, "Sub-actions are limited to one level")
    if not parent.requires_subaction:
        raise HTTPException(409, "Parent action must be marked as requiring sub-actions")
    return parent


def validate_action_hierarchy(action: Action, parent: Action | None) -> None:
    if action.state_effect != "EXIT" and (action.requires_subaction or parent is not None):
        raise HTTPException(409, "Only EXIT actions can use sub-actions")
    if action.requires_subaction and parent is not None:
        raise HTTPException(409, "A sub-action cannot require another sub-action")
    if not action.requires_subaction and action.subactions:
        raise HTTPException(409, "Remove or reassign child actions before disabling sub-actions")


def validate_actions(actions: list[Action], terminal_code: str, terminal_role: str = "CELL") -> None:
    if terminal_role != "CELL":
        return
    enabled = [action for action in actions if action.active and action.show_on_terminal]
    if sum(action.state_effect == "ENTER" for action in enabled) != 1:
        raise HTTPException(409, f"Terminal {terminal_code} requires exactly one active entry action")

    enabled_ids = {action.id for action in enabled if action.id is not None}
    top_level_exits = [
        action for action in enabled
        if action.state_effect == "EXIT" and (action.parent_action_id is None or action.parent_action_id not in enabled_ids)
    ]
    if not top_level_exits:
        raise HTTPException(409, f"Terminal {terminal_code} requires at least one active exit action")

    for parent in [action for action in top_level_exits if action.requires_subaction]:
        if not any(child.active and child.parent_action_id == parent.id for child in enabled):
            raise HTTPException(409, f"Terminal {terminal_code} requires at least one active sub-action for {parent.code}")


def commit_configuration(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Code, device ID or supplier event already exists")


def check_device_id(db: Session, device_id: str, terminal: Terminal | None = None) -> None:
    query = select(Terminal).where(Terminal.external_device_id == device_id)
    if terminal:
        query = query.where(Terminal.id != terminal.id)
    if db.scalar(query):
        raise HTTPException(409, "Oracle device ID already belongs to another terminal")


def check_supplier_event(db: Session, code: str, action: Action | None = None) -> None:
    query = select(Action).where(Action.supplier_device_event == code)
    if action:
        query = query.where(Action.id != action.id)
    if db.scalar(query):
        raise HTTPException(409, "Oracle supplier event already belongs to another action")
