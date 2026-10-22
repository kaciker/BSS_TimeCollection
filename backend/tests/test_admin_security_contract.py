from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.admin_security import install_admin_authentication


class DummyProvider:
    def __init__(self, authenticate, auth_endpoints=(), configured=True):
        self._authenticate = authenticate
        self._auth_endpoints = set(auth_endpoints)
        self._configured = configured

    @property
    def configured(self):
        return self._configured

    def authenticate(self, request):
        return self._authenticate(request)

    def is_authentication_endpoint(self, request):
        return (request.method, request.url.path) in self._auth_endpoints


def build_app(provider=None):
    app = FastAPI()
    install_admin_authentication(app, provider)

    @app.get("/api/v1/admin/example")
    def admin_endpoint():
        return {"ok": True}

    @app.post("/api/v1/admin/auth/login")
    def login_endpoint():
        return {"authenticated": True}

    @app.post("/api/v1/admin/auth/logout")
    def logout_endpoint():
        return {"authenticated": False}

    return app


def test_unauthenticated_admin_request_is_rejected():
    response = TestClient(build_app(DummyProvider(lambda request: None))).get("/api/v1/admin/example")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_invalid_credentials_are_rejected():
    def reject_invalid_credentials(request):
        return "admin" if request.headers.get("authorization") == "Bearer valid" else None

    client = TestClient(build_app(DummyProvider(reject_invalid_credentials)))
    response = client.get("/api/v1/admin/example", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401


def test_missing_authentication_provider_fails_closed():
    response = TestClient(build_app()).get("/api/v1/admin/example")
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_unconfigured_authentication_provider_fails_closed():
    provider = DummyProvider(lambda request: "admin", configured=False)
    response = TestClient(build_app(provider)).get("/api/v1/admin/example")
    assert response.status_code == 503


def test_provider_may_open_only_its_explicit_login_endpoint():
    provider = DummyProvider(
        lambda request: None,
        auth_endpoints={("POST", "/api/v1/admin/auth/login")},
    )
    client = TestClient(build_app(provider))
    assert client.post("/api/v1/admin/auth/login").status_code == 200
    assert client.post("/api/v1/admin/auth/logout").status_code == 401
