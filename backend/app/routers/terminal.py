from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.terminal import Terminal
from app.schemas.terminal import ActivationRequest, ExitRequest, ScanRequest, ScanResponse, TerminalAction, TerminalConfig
from app.services.event_service import record_exit, scan
from app.services.terminal_identity_service import COOKIE_NAME, activate_terminal, resolve_terminal_session

router = APIRouter(prefix="/api/v1/terminal", tags=["terminal"])


def _config(terminal: Terminal) -> TerminalConfig:
    actions = sorted([item for item in terminal.actions if item.active], key=lambda item: (item.display_order, item.id))
    return TerminalConfig(
        code=terminal.code,
        name=terminal.name,
        identification_mode=terminal.identification_mode,
        actions=[TerminalAction(code=item.code, label=item.label) for item in actions],
    )


@router.post("/activate", response_model=TerminalConfig)
def activate(payload: ActivationRequest, response: Response, db: Session = Depends(get_db)):
    terminal, session_token = activate_terminal(db, payload.token)
    max_age = int(timedelta(days=settings.terminal_session_days).total_seconds())
    response.set_cookie(
        COOKIE_NAME,
        session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.terminal_cookie_secure,
        samesite="strict",
        path="/",
    )
    return _config(terminal)


@router.get("/config", response_model=TerminalConfig)
def get_terminal_config(request: Request, db: Session = Depends(get_db)):
    return _config(resolve_terminal_session(db, request))


@router.post("/scan", response_model=ScanResponse)
def scan_badge(payload: ScanRequest, request: Request, db: Session = Depends(get_db)):
    terminal = resolve_terminal_session(db, request)
    return scan(db, terminal.code, payload.reporter_id.strip(), payload.identification_method)


@router.post("/exit", response_model=ScanResponse)
def register_exit(payload: ExitRequest, request: Request, db: Session = Depends(get_db)):
    terminal = resolve_terminal_session(db, request)
    return record_exit(db, terminal.code, payload.reporter_id.strip(), payload.identification_method, payload.action_code)
