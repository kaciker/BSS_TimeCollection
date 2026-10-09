from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.terminal import Terminal
from app.schemas.terminal import ExitRequest, ScanRequest, ScanResponse, TerminalAction, TerminalConfig
from app.services.event_service import record_exit, scan

router = APIRouter(prefix="/api/v1/terminal", tags=["terminal"])


@router.get("/{terminal_code}/config", response_model=TerminalConfig)
def get_terminal_config(terminal_code: str, db: Session = Depends(get_db)):
    terminal = db.scalar(select(Terminal).where(Terminal.code == terminal_code))
    if terminal is None or not terminal.active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terminal not found or inactive")
    actions = sorted([item for item in terminal.actions if item.active], key=lambda item: (item.display_order, item.id))
    return TerminalConfig(
        code=terminal.code,
        name=terminal.name,
        identification_mode=terminal.identification_mode,
        actions=[TerminalAction(code=item.code, label=item.label) for item in actions],
    )


@router.post("/{terminal_code}/scan", response_model=ScanResponse)
def scan_badge(terminal_code: str, payload: ScanRequest, db: Session = Depends(get_db)):
    return scan(db, terminal_code, payload.reporter_id.strip(), payload.identification_method)


@router.post("/{terminal_code}/exit", response_model=ScanResponse)
def register_exit(terminal_code: str, payload: ExitRequest, db: Session = Depends(get_db)):
    return record_exit(db, terminal_code, payload.reporter_id.strip(), payload.identification_method, payload.action_code)
