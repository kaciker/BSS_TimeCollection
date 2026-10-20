"""Factory presence and cascade regression tests."""
from sqlalchemy import select
from app.models.perimeter import FactoryPerimeterEvent
from app.models.time_event import TimeEvent
from test_configuration import configured_terminal, activate_created_terminal
from test_monitoring import monitor


def scan(client, badge="RFID-0001"):
    return client.post("/api/v1/terminal/scan", json={"reporter_id": badge, "identification_method": "KEYPAD"})


def setup_factory(client):
    cell, payload = configured_terminal(client)
    gate = client.post("/api/v1/admin/terminals", json={**payload, "code": "GATE", "external_device_id": "GATE"}).json()
    assert client.put("/api/v1/admin/perimeter/terminals/GATE/role", json={"factory_code": "DEFAULT", "role": "PERIMETER_BOTH"}).status_code == 200
    result = client.put("/api/v1/admin/perimeter/DEFAULT", json={
        "enabled": True, "badge_source": "OPEN", "dedup_enabled": True,
        "dedup_seconds": 5, "auto_exit_action_code": "STOP",
    })
    assert result.status_code == 200, result.text
    return cell, gate


def test_perimeter_required_and_cascade_queues_only_cell_exit(monitor):
    client, db = monitor
    cell, gate = setup_factory(client)
    token = client.post('/api/v1/admin/terminals/CLOCK-A/provision').json()['activation_token']
    assert client.post('/api/v1/terminal/activate', json={'token': token}).status_code == 200
    assert scan(client).status_code == 409
    assert db.scalars(select(TimeEvent)).all() == []
    activate_created_terminal(client, gate)
    assert scan(client).json()["flow"] == "FACTORY_ENTRY_RECORDED"
    assert db.scalars(select(TimeEvent)).all() == []
    token = client.post('/api/v1/admin/terminals/CLOCK-A/provision').json()['activation_token']
    assert client.post('/api/v1/terminal/activate', json={'token': token}).status_code == 200
    assert scan(client).json()["flow"] == "ENTRY_RECORDED"
    token = client.post('/api/v1/admin/terminals/GATE/provision').json()['activation_token']
    assert client.post('/api/v1/terminal/activate', json={'token': token}).status_code == 200
    result = scan(client)
    assert result.status_code == 200, result.text
    assert result.json()["flow"] == "FACTORY_EXIT_RECORDED"
    events = db.scalars(select(TimeEvent).order_by(TimeEvent.created_at)).all()
    assert len(events) == 2
    assert [e.state_effect for e in events] == ["ENTER", "EXIT"]
    assert all(e.delivery_status == "PENDING" for e in events)
    movements = db.scalars(select(FactoryPerimeterEvent).order_by(FactoryPerimeterEvent.event_datetime)).all()
    assert len(movements) == 2
    assert movements[-1].auto_cell_exit_event_id == events[-1].id
    token = client.post("/api/v1/admin/terminals/CLOCK-A/provision").json()["activation_token"]
    assert client.post("/api/v1/terminal/activate", json={"token": token}).status_code == 200
    assert scan(client).status_code == 409


def test_duplicate_and_open_uid(monitor):
    client, db = monitor
    cell, gate = setup_factory(client)
    client.put("/api/v1/admin/perimeter/terminals/GATE/role", json={"factory_code": "DEFAULT", "role": "PERIMETER_ENTER"})
    activate_created_terminal(client, gate)
    assert scan(client, "0000").json()["flow"] == "FACTORY_ENTRY_RECORDED"
    assert scan(client, "0000").json()["flow"] == "DUPLICATE_IGNORED"
    assert len(db.scalars(select(FactoryPerimeterEvent)).all()) == 1
    assert client.get("/api/v1/admin/perimeter/DEFAULT/presence").json()["inside"] == ["0000"]


def test_external_badge_source_not_activated(monitor):
    client, db = monitor
    configured_terminal(client)
    response = client.put("/api/v1/admin/perimeter/DEFAULT", json={
        "enabled": True, "badge_source": "EXTERNAL", "dedup_enabled": True,
        "dedup_seconds": 5, "auto_exit_action_code": "STOP",
    })
    assert response.status_code == 422
    assert client.get("/api/v1/admin/perimeter/DEFAULT").json()["enabled"] is False
