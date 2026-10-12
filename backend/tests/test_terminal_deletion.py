from sqlalchemy import select

from app.models.terminal import Terminal
from app.models.time_event import TimeEvent
from test_configuration import activate_created_terminal, configured_terminal
from test_monitoring import monitor


def test_remove_terminal_revokes_browser_and_preserves_events(monitor):
    client, db = monitor
    terminal, payload = configured_terminal(client)
    activate_created_terminal(client, terminal)
    event = client.post("/api/v1/terminal/scan", json={
        "reporter_id": "DELETION-TEST", "identification_method": "KEYPAD",
    }).json()["event"]
    assert client.delete("/api/v1/admin/terminals/CLOCK-A").status_code == 200
    assert client.get("/api/v1/admin/terminals").json() == []
    assert client.get("/api/v1/terminal/config").status_code == 401
    assert client.post("/api/v1/terminal/scan", json={
        "reporter_id": "DELETION-TEST", "identification_method": "KEYPAD",
    }).status_code == 401
    assert client.get("/api/v1/admin/monitoring/events?terminal_code=CLOCK-A").json()["total"] == 1
    assert "CLOCK-A" in client.get("/api/v1/admin/monitoring/clocks").json()
    assert client.get(f"/api/v1/admin/monitoring/events/{event['id']}").status_code == 200
    stored = db.scalar(select(Terminal).where(Terminal.code == "CLOCK-A"))
    assert stored.deleted_at is not None
    assert stored.active is False
    assert stored.session_token_hash is None
    assert db.get(TimeEvent, event["id"]).terminal_id == stored.id
    assert client.delete("/api/v1/admin/terminals/CLOCK-A").status_code == 404
    assert client.put("/api/v1/admin/terminals/CLOCK-A", json=payload).status_code == 404
    assert client.post("/api/v1/admin/terminals/CLOCK-A/clone").status_code == 404
    assert client.post("/api/v1/admin/terminals/CLOCK-A/provision").status_code == 404
    assert client.post("/api/v1/admin/terminals", json=payload).status_code == 409


def test_remove_unactivated_terminal_invalidates_activation_and_pairing(monitor):
    client, db = monitor
    terminal, _ = configured_terminal(client)
    pairing = client.post("/api/v1/terminal/pairing").json()
    assert client.post("/api/v1/admin/terminals/CLOCK-A/pair", json={"pairing_code": pairing["pairing_code"]}).status_code == 200
    assert client.delete("/api/v1/admin/terminals/CLOCK-A").status_code == 200
    assert client.post("/api/v1/terminal/activate", json={"token": terminal["activation_token"]}).status_code == 404
    assert client.post("/api/v1/terminal/pairing/status", json={"request_token": pairing["request_token"]}).status_code == 409
