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


def validate_actions(actions: list[Action], terminal_code: str) -> None:
    enabled = [action for action in actions if action.active]
    if sum(action.state_effect == "ENTER" for action in enabled) != 1:
        raise HTTPException(409, f"Terminal {terminal_code} requires exactly one active entry action")
    if not any(action.state_effect == "EXIT" for action in enabled):
        raise HTTPException(409, f"Terminal {terminal_code} requires at least one active exit action")


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
