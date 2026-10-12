from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.terminal import Terminal
from app.schemas.terminal import (
    ActivationRequest,
    ExitRequest,
    PairingPollRead,
    PairingPollRequest,
    PairingStartRead,
    ScanRequest,
    ScanResponse,
    TerminalAction,
    TerminalConfig,
)
from app.services.event_service import record_exit, scan
from app.services.terminal_identity_service import COOKIE_NAME, activate_terminal, resolve_terminal_session
from app.services.terminal_pairing_service import create_pairing_request, poll_pairing_request

router = APIRouter(prefix="/api/v1/terminal", tags=["terminal"])


def _config(terminal: Terminal) -> TerminalConfig:
    actions = sorted([item for item in terminal.actions if item.active], key=lambda item: (item.display_order, item.id))
    return TerminalConfig(
        code=terminal.code,
        name=terminal.name,
        identification_mode=terminal.identification_mode,
        actions=[TerminalAction(code=item.code, label=item.label) for item in actions],
    )


def _set_session_cookie(response: Response, session_token: str) -> None:
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


@router.post("/activate", response_model=TerminalConfig)
def activate(payload: ActivationRequest, response: Response, db: Session = Depends(get_db)):
    terminal, session_token = activate_terminal(db, payload.token)
    _set_session_cookie(response, session_token)
    return _config(terminal)


@router.post("/pairing", response_model=PairingStartRead, status_code=status.HTTP_201_CREATED)
def start_pairing(db: Session = Depends(get_db)):
    pairing, pairing_code, request_token = create_pairing_request(db)
    return PairingStartRead(
        pairing_code=pairing_code,
        request_token=request_token,
        expires_at=pairing.expires_at,
    )


@router.post("/pairing/status", response_model=PairingPollRead)
def pairing_status(payload: PairingPollRequest, response: Response, db: Session = Depends(get_db)):
    pairing_status_value, terminal, session_token = poll_pairing_request(db, payload.request_token)
    if terminal is None or session_token is None:
        return PairingPollRead(status=pairing_status_value)
    _set_session_cookie(response, session_token)
    return PairingPollRead(status=pairing_status_value, config=_config(terminal))


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
