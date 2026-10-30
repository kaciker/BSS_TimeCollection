import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core import oracle_credentials
from app.core.config import settings
from app.integrations.oracle.client import OracleClient
from app.main import app


@pytest.fixture
def credentials_file(tmp_path, monkeypatch):
    path = tmp_path / "oracle" / "credentials.json"
    monkeypatch.setattr(settings, "oracle_credentials_file", str(path))
    return path


def test_basic_credentials_are_saved_atomically_and_secret_free_in_responses(credentials_file):
    client = TestClient(app)
    response = client.put("/api/v1/admin/integration-credentials", json={
        "auth_mode": "basic", "username": "oracle-user", "password": "never-return-this",
    })
    assert response.status_code == 200
    assert response.json() == {
        "saved": True, "auth_mode": "basic", "username": "oracle-user",
        "password_configured": True, "bearer_token_configured": False,
        "credentials_configured": True,
    }
    assert "never-return-this" not in response.text
    assert credentials_file.stat().st_mode & 0o777 == 0o600
    assert credentials_file.parent.stat().st_mode & 0o777 == 0o700
    assert json.loads(credentials_file.read_text())["password"] == "never-return-this"
    get_response = client.get("/api/v1/admin/integration-settings")
    assert "never-return-this" not in get_response.text
    assert get_response.json()["password"] == "Configured"
    assert get_response.json()["bearer_token"] == "Not configured"


def test_bearer_credentials_never_return_secret(credentials_file):
    client = TestClient(app)
    response = client.put("/api/v1/admin/integration-credentials", json={
        "auth_mode": "bearer", "bearer_token": "private-bearer-token",
    })
    assert response.status_code == 200
    assert response.json()["bearer_token_configured"] is True
    assert "private-bearer-token" not in response.text
    assert "private-bearer-token" not in client.get("/api/v1/admin/integration-settings").text


def test_empty_secret_preserves_existing_and_explicit_replacement_works(credentials_file):
    oracle_credentials.configure_oracle_credentials(auth_mode="basic", username="user", password="original", bearer_token=None)
    oracle_credentials.configure_oracle_credentials(auth_mode="basic", username="renamed", password="", bearer_token=None)
    assert oracle_credentials.get_oracle_credentials()["password"] == "original"
    oracle_credentials.configure_oracle_credentials(auth_mode="basic", username=None, password="replacement", bearer_token=None)
    assert oracle_credentials.get_oracle_credentials()["password"] == "replacement"


@pytest.mark.parametrize("mode", ["None", "password", "digest", "invalid"])
def test_invalid_authentication_mode_is_rejected(mode, credentials_file):
    response = TestClient(app).put("/api/v1/admin/integration-credentials", json={"auth_mode": mode})
    assert response.status_code == 422


def test_explicit_clear_removes_active_secret(credentials_file):
    oracle_credentials.configure_oracle_credentials(auth_mode="bearer", username=None, password=None, bearer_token="secret")
    oracle_credentials.configure_oracle_credentials(auth_mode="bearer", username=None, password=None, bearer_token=None, clear_credentials=True)
    assert oracle_credentials.get_oracle_credentials()["bearer_token"] == ""


@pytest.mark.parametrize(("status_code", "expected_result", "expected_validated"), [
    (200, "authenticated", True),
    (401, "authentication_rejected", False),
    (403, "insufficient_privilege", False),
    (302, "http_error", False),
    (500, "oracle_error", False),
    (407, "proxy_error", False),
])
def test_authentication_test_uses_only_read_only_describe_get(
    credentials_file, monkeypatch, status_code, expected_result, expected_validated
):
    calls = []
    monkeypatch.setattr(settings, "oracle_base_url", "https://oracle.invalid")
    monkeypatch.setattr(settings, "oracle_api_path", "/hcmRestApi/resources/11.13.18.05/timeEventRequests")
    monkeypatch.setattr(settings, "oracle_rest_framework_version", "4")
    monkeypatch.setattr(settings, "oracle_timeout_seconds", 7)
    monkeypatch.setattr(settings, "oracle_enabled", False)
    oracle_credentials.configure_oracle_credentials(
        auth_mode="basic", username="oracle-user", password="private-test-password", bearer_token=None
    )

    class FakeResponse:
        def __init__(self):
            self.status_code = status_code

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def json(self):
            raise AssertionError("response body must not be read")

        @property
        def text(self):
            raise AssertionError("response body must not be read")

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(("client", kwargs))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def stream(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            return FakeResponse()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    client = TestClient(app)
    response = client.post("/api/v1/admin/integration-authentication-test", json={})
    result = response.json()

    assert response.status_code == 200
    assert result["result"] == expected_result
    assert result["validated"] is expected_validated
    assert result["http_status"] == status_code
    assert "private-test-password" not in response.text
    assert calls[0] == ("client", {"timeout": 7, "follow_redirects": False, "trust_env": True})
    method, url, kwargs = calls[1]
    assert method == "GET"
    assert url == "https://oracle.invalid/hcmRestApi/resources/11.13.18.05/timeEventRequests/describe"
    assert kwargs["headers"]["REST-Framework-Version"] == "4"
    assert isinstance(kwargs["auth"], httpx.BasicAuth)
    assert "Authorization" not in kwargs["headers"]
    assert settings.oracle_enabled is False
    assert method == "GET" and url.endswith("/timeEventRequests/describe")
    assert all(call[0] != "POST" for call in calls if len(call) == 3)


def test_authentication_test_uses_stored_bearer_and_classifies_transport_errors(credentials_file, monkeypatch):
    monkeypatch.setattr(settings, "oracle_base_url", "https://oracle.invalid")
    monkeypatch.setattr(settings, "oracle_enabled", False)
    oracle_credentials.configure_oracle_credentials(
        auth_mode="bearer", username=None, password=None, bearer_token="private-test-token"
    )
    calls = []

    class FakeResponse:
        status_code = 204
        def __enter__(self): return self
        def __exit__(self, *_args): return False

    class FakeClient:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def stream(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            return FakeResponse()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    response = TestClient(app).post("/api/v1/admin/integration-authentication-test", json={})
    assert response.json()["result"] == "authenticated"
    method, url, kwargs = calls[0]
    assert method == "GET" and url.endswith("/timeEventRequests/describe")
    assert kwargs["headers"]["Authorization"] == "Bearer private-test-token"
    assert kwargs["auth"] is None
    assert "private-test-token" not in response.text

    class ProxyErrorClient(FakeClient):
        def stream(self, *_args, **_kwargs):
            raise httpx.ProxyError("secret proxy detail must not escape")

    monkeypatch.setattr(httpx, "Client", ProxyErrorClient)
    result = TestClient(app).post("/api/v1/admin/integration-authentication-test", json={}).json()
    assert result["result"] == "proxy_error"
    assert "secret proxy detail" not in result["detail"]

    class TimeoutClient(FakeClient):
        def stream(self, *_args, **_kwargs):
            raise httpx.ReadTimeout("response included a secret and must not be returned")

    monkeypatch.setattr(httpx, "Client", TimeoutClient)
    result = TestClient(app).post("/api/v1/admin/integration-authentication-test", json={}).json()
    assert result["result"] == "timeout"
    assert "secret" not in result["detail"]

    class TLSClient(FakeClient):
        def stream(self, *_args, **_kwargs):
            error = httpx.ConnectError("TLS detail with secret")
            error.__cause__ = __import__("ssl").SSLError("private")
            raise error

    monkeypatch.setattr(httpx, "Client", TLSClient)
    result = TestClient(app).post("/api/v1/admin/integration-authentication-test", json={}).json()
    assert result["result"] == "tls_error"
    assert "secret" not in result["detail"] and "private" not in result["detail"]


def test_authentication_test_without_configured_credentials_never_contacts_oracle(credentials_file, monkeypatch):
    calls = []
    monkeypatch.setattr(settings, "oracle_base_url", "https://oracle.invalid")
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: calls.append(kwargs))
    result = TestClient(app).post("/api/v1/admin/integration-authentication-test", json={}).json()
    assert result["result"] == "credentials_missing"
    assert result["http_status"] is None
    assert calls == []


def test_host_connectivity_test_never_calls_time_event_endpoint(monkeypatch):
    calls = []
    monkeypatch.setattr(settings, "oracle_base_url", "https://oracle.invalid")
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: calls.append((args, kwargs)) or type("Response", (), {"status_code": 401})())
    result = TestClient(app).post("/api/v1/admin/integration-connection-test", json={}).json()
    assert result["reachable"] is True
    assert result["http_status"] == 401
    assert len(calls) == 1 and calls[0][0][0] == "https://oracle.invalid"
    assert "timeEventRequests" not in str(calls)

def test_worker_delivery_behavior_remains_disabled(credentials_file, monkeypatch):
    from app import worker
    called = []
    monkeypatch.setattr(settings, "oracle_enabled", False)
    monkeypatch.setattr(worker, "recover_stale_events", lambda: None)
    monkeypatch.setattr(worker, "sync_enabled_person_badges", lambda: None)
    monkeypatch.setattr(worker, "sync_enabled_external_perimeters", lambda: None)
    monkeypatch.setattr(worker, "reconcile_enabled_external_perimeters", lambda: None)
    monkeypatch.setattr(worker, "claim_next_event", lambda: called.append("claim") or "unexpected")
    monkeypatch.setattr(worker, "threading", type("FakeThreading", (), {
        "Event": staticmethod(lambda: type("Event", (), {"set": lambda self: None})()),
        "Thread": staticmethod(lambda *args, **kwargs: type("Thread", (), {"start": lambda self: None, "join": lambda self, timeout=None: None})()),
    })())
    monkeypatch.setattr(worker, "time", type("FakeTime", (), {
        "monotonic": staticmethod(lambda: 0),
        "sleep": staticmethod(lambda *_: (_ for _ in ()).throw(StopIteration())),
    })())
    with pytest.raises(StopIteration):
        worker.main()
    assert called == []
    assert settings.oracle_enabled is False


def test_oracle_client_uses_file_backed_auth_without_changing_delivery_flag(credentials_file):
    oracle_credentials.configure_oracle_credentials(auth_mode="bearer", username=None, password=None, bearer_token="client-secret")
    client = OracleClient()
    assert client._headers()["Authorization"] == "Bearer client-secret"
    assert client._auth() is None
    assert settings.oracle_enabled is False
