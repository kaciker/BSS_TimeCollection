import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.terminal import Terminal
from app.models.terminal_pairing_request import TerminalPairingRequest
from app.services.terminal_identity_service import bind_terminal_session

PAIRING_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
PAIRING_STATUS_PENDING = "PENDING"
PAIRING_STATUS_APPROVED = "APPROVED"
PAIRING_STATUS_CONSUMED = "CONSUMED"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_pairing_code(value: str) -> str:
    normalized = "".join(character for character in value.upper() if character.isalnum())
    if len(normalized) != 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pairing code must contain 8 characters")
    return normalized


def _new_pairing_code() -> tuple[str, str]:
    normalized = "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(8))
    return f"{normalized[:4]}-{normalized[4:]}", normalized


def _is_expired(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= datetime.now(timezone.utc)


def create_pairing_request(db: Session) -> tuple[TerminalPairingRequest, str, str]:
    now = datetime.now(timezone.utc)
    db.execute(delete(TerminalPairingRequest).where(
        TerminalPairingRequest.expires_at <= now,
        TerminalPairingRequest.status != PAIRING_STATUS_CONSUMED,
    ))
    request_token = secrets.token_urlsafe(32)
    for _ in range(20):
        display_code, normalized_code = _new_pairing_code()
        if db.scalar(select(TerminalPairingRequest.id).where(TerminalPairingRequest.code_hash == _hash(normalized_code))) is None:
            break
    else:
        raise HTTPException(status_code=503, detail="Could not allocate a pairing code")
    pairing = TerminalPairingRequest(
        code_hash=_hash(normalized_code),
        request_token_hash=_hash(request_token),
        status=PAIRING_STATUS_PENDING,
        expires_at=now + timedelta(minutes=settings.terminal_pairing_minutes),
    )
    db.add(pairing)
    db.commit()
    db.refresh(pairing)
    return pairing, display_code, request_token


def approve_pairing_request(db: Session, terminal: Terminal, pairing_code: str) -> TerminalPairingRequest:
    normalized_code = _normalize_pairing_code(pairing_code)
    pairing = db.scalar(
        select(TerminalPairingRequest)
        .where(TerminalPairingRequest.code_hash == _hash(normalized_code))
        .with_for_update()
    )
    if pairing is None:
        raise HTTPException(status_code=404, detail="Pairing code not found")
    if _is_expired(pairing.expires_at):
        raise HTTPException(status_code=410, detail="Pairing code has expired")
    if pairing.status != PAIRING_STATUS_PENDING:
        raise HTTPException(status_code=409, detail="Pairing code has already been used")
    if not terminal.active or terminal.deleted_at is not None:
        raise HTTPException(status_code=409, detail="Inactive terminals cannot be paired")
    pairing.terminal_id = terminal.id
    pairing.status = PAIRING_STATUS_APPROVED
    pairing.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(pairing)
    return pairing


def poll_pairing_request(db: Session, request_token: str) -> tuple[str, Terminal | None, str | None]:
    pairing = db.scalar(
        select(TerminalPairingRequest)
        .where(TerminalPairingRequest.request_token_hash == _hash(request_token))
        .with_for_update()
    )
    if pairing is None:
        raise HTTPException(status_code=404, detail="Pairing request not found")
    if _is_expired(pairing.expires_at):
        raise HTTPException(status_code=410, detail="Pairing code has expired")
    if pairing.status == PAIRING_STATUS_PENDING:
        return "WAITING", None, None
    if pairing.status == PAIRING_STATUS_CONSUMED:
        raise HTTPException(status_code=409, detail="Pairing request has already been consumed")
    if pairing.status != PAIRING_STATUS_APPROVED or pairing.terminal_id is None:
        raise HTTPException(status_code=409, detail="Pairing request is in an invalid state")
    terminal = db.scalar(select(Terminal).where(Terminal.id == pairing.terminal_id).with_for_update())
    if terminal is None or not terminal.active or terminal.deleted_at is not None:
        raise HTTPException(status_code=409, detail="Assigned terminal is unavailable")
    session_token = bind_terminal_session(terminal)
    pairing.status = PAIRING_STATUS_CONSUMED
    pairing.consumed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(terminal)
    return "APPROVED", terminal, session_token
