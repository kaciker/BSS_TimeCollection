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



def test_temporary_provider_only_exempts_login():
    from fastapi import Request
    from app.core.admin_auth import provider

    login = Request({
        "type": "http", "method": "POST", "path": "/api/v1/admin/auth/login",
        "headers": [], "query_string": b"", "server": ("test", 80),
        "client": ("test", 1), "scheme": "http",
    })
    logout = Request({
        "type": "http", "method": "POST", "path": "/api/v1/admin/auth/logout",
        "headers": [], "query_string": b"", "server": ("test", 80),
        "client": ("test", 1), "scheme": "http",
    })

    assert provider.is_authentication_endpoint(login)
    assert not provider.is_authentication_endpoint(logout)


def test_missing_temporary_auth_configuration_fails_closed(monkeypatch):
    import pytest
    from fastapi import HTTPException, status
    from app.core import admin_auth

    monkeypatch.setattr(admin_auth.settings, "admin_username", "")
    monkeypatch.setattr(admin_auth.settings, "admin_password_hash", "")
    monkeypatch.setattr(admin_auth.settings, "admin_session_secret", "")
    with pytest.raises(HTTPException) as error:
        admin_auth.ensure_auth_configured()
    assert error.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

def test_missing_configuration_rejects_protected_requests(monkeypatch):
    import pytest
    from fastapi import HTTPException, Request, status
    from app.core.admin_auth import provider
    from app.core import admin_auth

    monkeypatch.setattr(admin_auth.settings, "admin_username", "")
    monkeypatch.setattr(admin_auth.settings, "admin_password_hash", "")
    monkeypatch.setattr(admin_auth.settings, "admin_session_secret", "")
    request = Request({
        "type": "http", "method": "GET", "path": "/api/v1/admin/actions",
        "headers": [], "query_string": b"", "server": ("test", 80),
        "client": ("test", 1), "scheme": "http",
    })
    with pytest.raises(HTTPException) as error:
        provider.authenticate(request)
    assert error.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


def _auth_test_app():
    from fastapi import FastAPI
    from app.core.admin_auth import provider, router
    from app.core.admin_security import install_admin_authentication

    app = FastAPI()
    install_admin_authentication(app, provider)
    app.include_router(router)

    @app.get("/api/v1/admin/probe")
    def protected_probe():
        return {"authenticated": True}

    return app


def test_invalid_login_credentials_never_open_admin(monkeypatch):
    from fastapi.testclient import TestClient
    from app.core import admin_auth

    monkeypatch.setattr(admin_auth.settings, "admin_username", "admin")
    monkeypatch.setattr(admin_auth.settings, "admin_password_hash", _password_hash("right"))
    monkeypatch.setattr(admin_auth.settings, "admin_session_secret", "test-session-secret")
    client = TestClient(_auth_test_app())

    response = client.post("/api/v1/admin/auth/login", json={"username": "admin", "password": "wrong"})
    assert response.status_code == 401
    assert client.get("/api/v1/admin/probe").status_code == 401


def test_valid_login_authenticates_protected_admin_route(monkeypatch):
    from fastapi.testclient import TestClient
    from app.core import admin_auth

    monkeypatch.setattr(admin_auth.settings, "admin_username", "admin")
    monkeypatch.setattr(admin_auth.settings, "admin_password_hash", _password_hash("right"))
    monkeypatch.setattr(admin_auth.settings, "admin_session_secret", "test-session-secret")
    client = TestClient(_auth_test_app())

    login = client.post("/api/v1/admin/auth/login", json={"username": "admin", "password": "right"})
    assert login.status_code == 200
    assert client.get("/api/v1/admin/probe").json() == {"authenticated": True}


def test_missing_authentication_configuration_rejects_login_and_admin(monkeypatch):
    from fastapi.testclient import TestClient
    from app.core import admin_auth

    monkeypatch.setattr(admin_auth.settings, "admin_username", "")
    monkeypatch.setattr(admin_auth.settings, "admin_password_hash", "")
    monkeypatch.setattr(admin_auth.settings, "admin_session_secret", "")
    client = TestClient(_auth_test_app())

    assert client.post(
        "/api/v1/admin/auth/login", json={"username": "admin", "password": "anything"}
    ).status_code == 503
    assert client.get("/api/v1/admin/probe").status_code == 503
