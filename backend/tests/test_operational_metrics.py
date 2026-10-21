from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import worker
from app.core.config import settings
from app.db.base import Base
from app.main import app
from app.models.worker_runtime_metrics import WorkerRuntimeMetrics
from app.routers import health


def test_operational_route_requires_long_machine_bearer_and_hides_errors(monkeypatch):
    monkeypatch.setattr(settings, "operational_metrics_token", "s" * 32)
    with patch.object(health, "collect_operational_metrics", return_value={"contract_version": 1}):
        client = TestClient(app)
        assert client.get("/api/v1/health/operational").status_code == 401
        assert client.get("/api/v1/health/operational", headers={"Authorization": "Bearer wrong"}).status_code == 401
        response = client.get("/api/v1/health/operational", headers={"Authorization": "Bearer " + "s" * 32})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"

    with patch.object(health, "collect_operational_metrics", side_effect=RuntimeError("private payload")):
        response = TestClient(app).get("/api/v1/health/operational", headers={"Authorization": "Bearer " + "s" * 32})
        assert response.status_code == 503
        assert "private payload" not in response.text


def test_runtime_metric_upsert_preserves_success_timestamps(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(worker, "SessionLocal", lambda: Session(engine))
    worker.update_runtime_metrics(heartbeat=True, successful_cycle=True, successful_delivery=True)
    with Session(engine) as db:
        initial = db.get(WorkerRuntimeMetrics, 1)
        delivery = initial.last_successful_delivery_at
        cycle = initial.last_successful_cycle_at
        heartbeat = initial.heartbeat_at
    worker.update_runtime_metrics(heartbeat=True)
    with Session(engine) as db:
        updated = db.get(WorkerRuntimeMetrics, 1)
        assert updated.heartbeat_at >= heartbeat
        assert updated.last_successful_cycle_at == cycle
        assert updated.last_successful_delivery_at == delivery
    engine.dispose()


def test_worker_metric_update_failure_does_not_claim_success(monkeypatch):
    class FailedSession:
        def __enter__(self):
            raise RuntimeError("database unavailable")
        def __exit__(self, *args):
            pass
    monkeypatch.setattr(worker, "SessionLocal", FailedSession)
    try:
        worker.update_runtime_metrics(successful_cycle=True)
    except RuntimeError:
        pass
    else:
        raise AssertionError("failed DB update must not report a completed metric write")
