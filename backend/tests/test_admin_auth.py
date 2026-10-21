import base64
import hashlib

from app.core import admin_auth


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _password_hash(password: str) -> str:
    iterations = 210000
    salt = b"temporary-admin-auth-test-salt"
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_encode(salt)}${_encode(digest)}"


def test_password_hash_verification():
    encoded = _password_hash("correct-password")
    assert admin_auth.verify_password("correct-password", encoded)
    assert not admin_auth.verify_password("wrong-password", encoded)


def test_session_token_roundtrip(monkeypatch):
    monkeypatch.setattr(admin_auth.settings, "admin_username", "admin")
    monkeypatch.setattr(admin_auth.settings, "admin_session_secret", "test-secret-with-enough-entropy")
    monkeypatch.setattr(admin_auth.settings, "admin_session_hours", 8)
    token = admin_auth.make_session_token("admin")
    assert admin_auth.validate_session_token(token) == "admin"
    assert admin_auth.validate_session_token(token + "x") is None
