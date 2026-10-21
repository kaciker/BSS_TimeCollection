from fastapi import Request
from fastapi.testclient import TestClient

from app.main import app


class HeaderAdminProvider:
    @property
    def configured(self) -> bool:
        return getattr(self, "_configured", True)

    @configured.setter
    def configured(self, value: bool) -> None:
        self._configured = value

    def authenticate(self, request: Request) -> str | None:
        if request.headers.get("authorization") == "Bearer valid-test-admin":
            return "test-admin"
        return None


def test_admin_request_fails_closed_when_provider_is_missing():
    previous = getattr(app.state, "admin_auth_provider", None)
    if hasattr(app.state, "admin_auth_provider"):
        delattr(app.state, "admin_auth_provider")
    try:
        response = TestClient(app).get("/api/v1/admin/integration-settings")
        assert response.status_code == 503
        assert response.json()["detail"] == "Admin authentication provider is not configured."
    finally:
        if previous is not None:
            app.state.admin_auth_provider = previous


def test_admin_request_fails_closed_when_provider_is_unconfigured():
    previous = getattr(app.state, "admin_auth_provider", None)
    provider = HeaderAdminProvider()
    provider.configured = False
    app.state.admin_auth_provider = provider
    try:
        response = TestClient(app).get("/api/v1/admin/integration-settings")
        assert response.status_code == 503
    finally:
        if previous is None:
            delattr(app.state, "admin_auth_provider")
        else:
            app.state.admin_auth_provider = previous


def test_admin_request_rejects_unauthenticated_and_invalid_credentials():
    previous = getattr(app.state, "admin_auth_provider", None)
    app.state.admin_auth_provider = HeaderAdminProvider()
    try:
        client = TestClient(app)
        unauthenticated = client.get("/api/v1/admin/integration-settings")
        invalid = client.get("/api/v1/admin/integration-settings",
                             headers={"Authorization": "Bearer invalid"})
        assert unauthenticated.status_code == 401
        assert invalid.status_code == 401
    finally:
        if previous is None:
            delattr(app.state, "admin_auth_provider")
        else:
            app.state.admin_auth_provider = previous


def test_admin_request_accepts_valid_provider_credentials():
    previous = getattr(app.state, "admin_auth_provider", None)
    app.state.admin_auth_provider = HeaderAdminProvider()
    try:
        response = TestClient(app).get("/api/v1/admin/integration-settings",
                                      headers={"Authorization": "Bearer valid-test-admin"})
        assert response.status_code == 200
        assert response.request.headers["authorization"] == "Bearer valid-test-admin"
    finally:
        if previous is None:
            delattr(app.state, "admin_auth_provider")
        else:
            app.state.admin_auth_provider = previous
