from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import worker
from app.core.config import settings
from app.db.base import Base
from app.main import app
from app.models.perimeter import FactoryPerimeterEvent
from app.models.time_event import TimeEvent
from app.models.transmission_attempt import TransmissionAttempt
from app.models.worker_runtime_metrics import WorkerRuntimeMetrics
from app.routers import health
from app.services import operational_metrics


def test_operational_route_requires_bearer_and_hides_errors(monkeypatch):
    monkeypatch.setattr(settings, "operational_metrics_token", "s" * 32)
    with patch.object(health, "collect_operational_metrics", return_value={"contract_version": 1}):
        client = TestClient(app)
        assert client.get("/api/v1/health/operational").status_code == 401
        assert client.get("/api/v1/health/operational", headers={"Authorization": "Bearer wrong"}).status_code == 401
        response = client.get("/api/v1/health/operational", headers={"Authorization": "Bearer " + "s" * 32})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
    with patch.object(health, "collect_operational_metrics", side_effect=RuntimeError("private payload")):
        response = TestClient(app).get(
            "/api/v1/health/operational", headers={"Authorization": "Bearer " + "s" * 32}
        )
        assert response.status_code == 503
        assert "private payload" not in response.text


def test_authenticated_route_returns_complete_v1_contract(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(operational_metrics, "engine", engine)
    monkeypatch.setattr(health, "collect_operational_metrics", operational_metrics.collect_operational_metrics)
    monkeypatch.setattr(settings, "operational_metrics_token", "t" * 40)
    monkeypatch.setattr(settings, "oracle_enabled", False)

    response = TestClient(app).get(
        "/api/v1/health/operational", headers={"Authorization": "Bearer " + "t" * 40}
    )
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "contract_version", "collected_at", "oracle", "worker", "events",
        "transmission_attempts_24h", "perimeter_24h",
    }
    assert payload["contract_version"] == 1
    assert payload["oracle"] == {"status": "DISABLED"}
    assert payload["worker"]["processing_status"] == "DISABLED"
    assert set(payload["events"]["by_delivery_status"]) == {
        "PENDING", "RETRY", "SENDING", "SENT", "REJECTED", "UNKNOWN",
    }
    assert payload["transmission_attempts_24h"]["window_seconds"] == 86400
    assert payload["perimeter_24h"]["window_seconds"] == 86400
    engine.dispose()


def test_runtime_metric_upsert_preserves_success_timestamps(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(worker, "SessionLocal", lambda: Session(engine))
    worker.update_runtime_metrics(heartbeat=True, successful_cycle=True, successful_delivery=True)
    with Session(engine) as db:
        initial = db.get(WorkerRuntimeMetrics, 1)
        delivery, cycle, heartbeat = initial.last_successful_delivery_at, initial.last_successful_cycle_at, initial.heartbeat_at
    worker.update_runtime_metrics(heartbeat=True)
    with Session(engine) as db:
        updated = db.get(WorkerRuntimeMetrics, 1)
        assert updated.heartbeat_at >= heartbeat
        assert updated.last_successful_cycle_at == cycle
        assert updated.last_successful_delivery_at == delivery
    worker.update_runtime_metrics(process_started=True, heartbeat=True)
    with Session(engine) as db:
        restarted = db.get(WorkerRuntimeMetrics, 1)
        assert restarted.process_started_at >= initial.process_started_at
    engine.dispose()


def test_cycle_metric_failure_does_not_interrupt_existing_worker_services(monkeypatch):
    calls = []

    monkeypatch.setattr(worker, "recover_stale_events", lambda: calls.append("recover"))
    monkeypatch.setattr(worker, "OracleClient", lambda: object())
    monkeypatch.setattr(worker, "sync_enabled_external_perimeters", lambda: calls.append("sync") or 0)
    monkeypatch.setattr(worker, "reconcile_enabled_external_perimeters", lambda: calls.append("reconcile") or 0)
    monkeypatch.setattr(worker.settings, "oracle_enabled", True)
    monkeypatch.setattr(worker.settings, "worker_heartbeat_seconds", 1)
    monkeypatch.setattr(worker, "update_runtime_metrics", lambda **kwargs: (_ for _ in ()).throw(RuntimeError()))
    monkeypatch.setattr(worker.time, "sleep", lambda _seconds: None)

    def claim():
        calls.append("claim")
        return "safe-test-event"

    def deliver(event_id, _client):
        calls.append(("deliver", event_id))
        raise KeyboardInterrupt()

    monkeypatch.setattr(worker, "claim_next_event", claim)
    monkeypatch.setattr(worker, "deliver", deliver)
    try:
        worker.main()
    except KeyboardInterrupt:
        pass

    assert "sync" in calls and "reconcile" in calls
    assert ("deliver", "safe-test-event") in calls


def test_worker_advances_cycle_metric_after_successful_queue_claim(monkeypatch):
    metrics = []
    monkeypatch.setattr(worker, "recover_stale_events", lambda: None)
    monkeypatch.setattr(worker, "OracleClient", lambda: object())
    monkeypatch.setattr(worker, "sync_enabled_external_perimeters", lambda: 0)
    monkeypatch.setattr(worker, "reconcile_enabled_external_perimeters", lambda: 0)
    monkeypatch.setattr(worker.settings, "oracle_enabled", True)
    monkeypatch.setattr(worker.settings, "worker_heartbeat_seconds", 1)
    monkeypatch.setattr(worker.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(worker, "update_runtime_metrics", lambda **kwargs: metrics.append(kwargs))
    monkeypatch.setattr(worker, "claim_next_event", lambda: "safe-test-event")

    def stop_after_delivery(_event_id, _client):
        raise KeyboardInterrupt()

    monkeypatch.setattr(worker, "deliver", stop_after_delivery)
    try:
        worker.main()
    except KeyboardInterrupt:
        pass
    assert {"successful_cycle": True} in metrics
    assert any(entry.get("heartbeat") is True for entry in metrics)


def test_aggregate_contract_excludes_record_data_and_reports_disabled_oracle(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(operational_metrics, "engine", engine)
    monkeypatch.setattr(settings, "oracle_enabled", False)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with Session(engine) as db:
        db.add(WorkerRuntimeMetrics(id=1, process_started_at=now, heartbeat_at=now, last_successful_cycle_at=now))
        db.add(FactoryPerimeterEvent(
            id="privacy-event", factory_code="ARGANDA", reporter_id="badge-private", terminal_id=1,
            direction="ENTER", event_datetime=now, correlation_id="correlation-private",
        ))
        db.commit()
    result = operational_metrics.collect_operational_metrics()
    assert result["contract_version"] == 1
    assert result["oracle"]["status"] == "DISABLED"
    assert result["worker"]["process_status"] == "RUNNING"
    assert result["worker"]["processing_status"] == "DISABLED"
    assert result["perimeter_24h"]["local_only_count"] == 1
    assert "badge-private" not in str(result) and "privacy-event" not in str(result)
    engine.dispose()


def test_aggregate_queue_attempt_and_perimeter_window_counts(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(operational_metrics, "engine", engine)
    monkeypatch.setattr(settings, "oracle_enabled", True)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with Session(engine) as db:
        event = TimeEvent(
            id="event-id", request_number="request-id", terminal_id=1, action_id=1, terminal_code="T1",
            device_id="device", action_code="A", action_label="Action", supplier_device_event="event",
            state_effect="ENTER", reporter_id="badge", reporter_id_type="BADGE", identification_method="RFID",
            event_datetime=now, event_timezone="UTC", oracle_attributes={"secret": "record"},
            delivery_status="PENDING", created_at=now - timedelta(minutes=2),
        )
        db.add(event)
        db.add(TransmissionAttempt(
            event_id=event.id, attempt_number=1, started_at=now - timedelta(minutes=1), finished_at=now,
            endpoint="private-endpoint", http_status=200, result="SENT", duration_ms=1,
            request_payload={"private": True}, response_payload=None, error_message=None,
        ))
        db.add(FactoryPerimeterEvent(
            id="movement-id", factory_code="ARGANDA", reporter_id="badge", terminal_id=1,
            direction="EXIT", event_datetime=now - timedelta(hours=1), correlation_id="c",
        ))
        db.add(FactoryPerimeterEvent(
            id="old-movement", factory_code="ARGANDA", reporter_id="badge", terminal_id=1,
            direction="EXIT", event_datetime=now - timedelta(days=2), correlation_id="c2",
        ))
        db.commit()
    result = operational_metrics.collect_operational_metrics()
    assert result["events"]["pending_count"] == 1
    assert result["events"]["oldest_pending_age_seconds"] >= 119
    assert result["transmission_attempts_24h"]["by_result"]["SENT"] == 1
    assert result["transmission_attempts_24h"]["total"] == 1
    assert result["perimeter_24h"]["local_only_count"] == 1
    assert "event-id" not in str(result) and "private-endpoint" not in str(result) and "record" not in str(result)
    engine.dispose()
