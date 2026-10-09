import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.terminal import Terminal

COOKIE_NAME = "bss_terminal_session"


def _hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def issue_activation_token(terminal: Terminal) -> str:
    token = _new_token()
    terminal.activation_token_hash = _hash_token(token)
    terminal.session_token_hash = None
    terminal.activated_at = None
    return token


def activate_terminal(db: Session, token: str) -> tuple[Terminal, str]:
    # Lock the matching row so concurrent requests cannot consume the same token.
    # PostgreSQL rechecks the predicate after the previous consumer commits.
    terminal = db.scalar(
        select(Terminal)
        .where(Terminal.activation_token_hash == _hash_token(token))
        .with_for_update()
    )
    if terminal is None or not terminal.active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activation token is invalid, expired or disabled")
    session_token = _new_token()
    terminal.activation_token_hash = None
    terminal.session_token_hash = _hash_token(session_token)
    terminal.activated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(terminal)
    return terminal, session_token


def resolve_terminal_session(db: Session, request: Request) -> Terminal:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="This browser is not provisioned as a terminal")
    terminal = db.scalar(select(Terminal).where(Terminal.session_token_hash == _hash_token(token)))
    if terminal is None or not terminal.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Terminal session is invalid, revoked or disabled")
    terminal.last_seen_at = datetime.now(timezone.utc)
    terminal.last_ip = request.client.host if request.client else None
    terminal.last_user_agent = request.headers.get("user-agent", "")[:512] or None
    db.commit()
    return terminal
