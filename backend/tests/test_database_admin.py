from app.core.config import settings
from test_monitoring import monitor


def test_database_status_never_exposes_password(monitor):
    client, _ = monitor
    response = client.get("/api/v1/admin/database")
    assert response.status_code == 200
    body = response.json()
    assert "password" not in body
    assert body["backend"] == "postgresql"


def test_external_database_test_requires_explicit_enable(monitor):
    client, _ = monitor
    original = settings.database_admin_test_enabled
    settings.database_admin_test_enabled = False
    try:
        response = client.post("/api/v1/admin/database/test", json={
            "host": "db.example.local",
            "port": 5432,
            "database": "bss_timecollection",
            "username": "bss_timecollection",
            "password": "secret-value",
            "sslmode": "require",
        })
        assert response.status_code == 403
        assert "disabled" in response.json()["detail"].lower()
    finally:
        settings.database_admin_test_enabled = original
