"""File-backed Oracle credentials with environment fallback compatibility."""

import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any

from app.core.config import settings

_lock = RLock()
_ALLOWED_MODES = {"none", "basic", "bearer"}


def _environment_values() -> dict[str, str]:
    return {
        "auth_mode": settings.oracle_auth_mode.strip().lower(),
        "username": settings.oracle_username,
        "password": settings.oracle_password,
        "bearer_token": settings.oracle_bearer_token,
    }


def get_oracle_credentials() -> dict[str, str]:
    """Read file values when present. Callers must never expose this result in API output."""
    path = Path(settings.oracle_credentials_file)
    with _lock:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("Oracle credentials file must contain an object")
            values = _environment_values()
            values.update({key: value for key, value in raw.items() if key in values and isinstance(value, str)})
        except FileNotFoundError:
            values = _environment_values()
    mode = values["auth_mode"].lower()
    values["auth_mode"] = mode if mode in _ALLOWED_MODES else "none"
    return values


def credential_state() -> dict[str, Any]:
    values = get_oracle_credentials()
    mode = values["auth_mode"]
    return {
        "auth_mode": mode,
        "username": values["username"] if mode == "basic" else "",
        "password_configured": bool(values["password"]) if mode == "basic" else False,
        "bearer_token_configured": bool(values["bearer_token"]) if mode == "bearer" else False,
        "credentials_configured": (bool(values["username"] and values["password"]) if mode == "basic" else bool(values["bearer_token"]) if mode == "bearer" else False),
    }


def configure_oracle_credentials(*, auth_mode: str, username: str | None, password: str | None, bearer_token: str | None, clear_credentials: bool = False) -> dict[str, Any]:
    mode = auth_mode.strip().lower()
    if mode not in _ALLOWED_MODES:
        raise ValueError("Authentication mode must be none, basic, or bearer")
    path = Path(settings.oracle_credentials_file)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    with _lock:
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                existing = {}
        except FileNotFoundError:
            existing = _environment_values()
        except (OSError, ValueError):
            existing = _environment_values()
        values = {key: str(existing.get(key, "")) for key in ("auth_mode", "username", "password", "bearer_token")}
        values["auth_mode"] = mode
        if mode == "basic":
            if username is not None:
                values["username"] = username.strip()
            if clear_credentials:
                values["password"] = ""
            elif password:
                values["password"] = password
        elif mode == "bearer":
            if clear_credentials:
                values["bearer_token"] = ""
            elif bearer_token:
                values["bearer_token"] = bearer_token
        payload = json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        fd, temporary_name = tempfile.mkstemp(prefix=".oracle-credentials-", dir=path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, path)
            os.chmod(path, 0o600)
            directory_fd = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
    return credential_state()
