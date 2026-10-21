"""Provider-independent contract and temporary Admin credential provider."""

import base64
import hashlib
import hmac
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Protocol, runtime_checkable

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.core.config import settings

COOKIE_NAME = "bss_admin_session"
_HASH_SCHEME = "pbkdf2_sha256"
_failed_logins: dict[str, deque[float]] = defaultdict(deque)
_failed_logins_lock = Lock()


@runtime_checkable
class FailClosedAdminAuthProvider(Protocol):
    @property
    def configured(self) -> bool: ...

    def authenticate(self, request: Request) -> str | None: ...


AdminAuthProvider = FailClosedAdminAuthProvider


class LoginRequest(BaseModel):
    username: str
    password: str


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        scheme, iterations_text, salt_text, expected_text = encoded_hash.split("$", 3)
        if scheme != _HASH_SCHEME:
            return False
        iterations = int(iterations_text)
        salt = _b64decode(salt_text)
        expected = _b64decode(expected_text)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def make_session_token(username: str) -> str:
    expires_at = int(time.time()) + int(settings.admin_session_hours * 3600)
    payload = f"{username}|{expires_at}".encode("utf-8")
    signature = hmac.new(settings.admin_session_secret.encode("utf-8"), payload, hashlib.sha256).digest()
    return f"{_b64encode(payload)}.{_b64encode(signature)}"


def validate_session_token(token: str | None) -> str | None:
    if not token or not settings.admin_session_secret:
        return None
    try:
        payload_text, signature_text = token.split(".", 1)
        payload = _b64decode(payload_text)
        signature = _b64decode(signature_text)
        expected = hmac.new(settings.admin_session_secret.encode("utf-8"), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return None
        username, expires_text = payload.decode("utf-8").rsplit("|", 1)
        if int(expires_text) <= int(time.time()):
            return None
        if not hmac.compare_digest(username, settings.admin_username):
            return None
        return username
    except (ValueError, UnicodeDecodeError):
        return None


def authenticated_admin(request: Request) -> str | None:
    return validate_session_token(request.cookies.get(COOKIE_NAME))


class TemporaryAdminAuthProvider:
    @property
    def configured(self) -> bool:
        return bool(settings.admin_auth_enabled and settings.admin_username
                    and settings.admin_password_hash and settings.admin_session_secret)

    def authenticate(self, request: Request) -> str | None:
        return authenticated_admin(request)


def _rate_limit_key(request: Request, username: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{host}:{username.strip().lower()}"


def _check_rate_limit(key: str) -> None:
    now = time.monotonic()
    window = float(settings.admin_login_window_seconds)
    with _failed_logins_lock:
        attempts = _failed_logins[key]
        while attempts and now - attempts[0] > window:
            attempts.popleft()
        if len(attempts) >= settings.admin_login_max_attempts:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many login attempts. Try again later.")


def _record_failed_login(key: str) -> None:
    with _failed_logins_lock:
        _failed_logins[key].append(time.monotonic())


def _clear_failed_logins(key: str) -> None:
    with _failed_logins_lock:
        _failed_logins.pop(key, None)


def ensure_auth_configured() -> None:
    if not settings.admin_username or not settings.admin_password_hash or not settings.admin_session_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Temporary admin authentication is not configured.")


router = APIRouter(prefix="/api/v1/auth/admin", tags=["admin-auth"])


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response):
    ensure_auth_configured()
    key = _rate_limit_key(request, payload.username)
    _check_rate_limit(key)
    username_ok = hmac.compare_digest(payload.username, settings.admin_username)
    password_ok = verify_password(payload.password, settings.admin_password_hash)
    if not username_ok or not password_ok:
        _record_failed_login(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials.")
    _clear_failed_logins(key)
    max_age = int(settings.admin_session_hours * 3600)
    response.set_cookie(COOKIE_NAME, make_session_token(settings.admin_username), max_age=max_age,
                        httponly=True, secure=settings.admin_cookie_secure, samesite="strict", path="/")
    return {"authenticated": True, "username": settings.admin_username}


@router.get("/me")
def me(request: Request):
    username = authenticated_admin(request)
    return {"authenticated": username is not None, "username": username}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"authenticated": False}
