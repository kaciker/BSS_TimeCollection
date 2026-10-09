from datetime import datetime, timezone

from sqlalchemy import select

from test_monitoring import monitor
from app.models.time_event import TimeEvent
from app.models.terminal import Terminal


def create_action(client, code, effect="EXIT", oracle_attributes=None):
    response = client.post("/api/v1/admin/actions", json={
        "code": code, "label": code.title(), "supplier_device_event": f"BSS_{code}",
        "state_effect": effect, "display_order": 10, "oracle_attributes": oracle_attributes or {},
    })
    assert response.status_code == 201, response.text
    return response.json()


def configured_terminal(client, code="CLOCK-A"):
    create_action(client, "START", "ENTER")
    create_action(client, "STOP")
    payload = {
        "code": code,
        "name": "North gate",
        "external_device_id": code,
        "identification_mode": "BOTH",
        "reporter_id_type": "BADGE",
        "oracle_attributes": {"Workshop": "Assembly", "Project": "P42"},
        "active": True,
        "action_codes": ["START", "STOP"],
    }
    response = client.post("/api/v1/admin/terminals", json=payload)
    assert response.status_code == 201, response.text
    return response.json(), payload


def activate_created_terminal(client, terminal):
    response = client.post("/api/v1/terminal/activate", json={"token": terminal["activation_token"]})
    assert response.status_code == 200, response.text
    return response.json()


def test_create_terminal_persists_configuration_and_duplicate_device_is_readable(monitor):
    client, db = monitor
    terminal, payload = configured_terminal(client)
    assert terminal["action_codes"] == ["START", "STOP"]
    assert terminal["oracle_attributes"]["Workshop"] == "Assembly"
    assert terminal["activation_token"]
    response = client.post("/api/v1/admin/terminals", json={**payload, "code": "CLOCK-B"})
    assert response.status_code == 409
    assert "device ID" in response.json()["detail"]
    assert len(client.get("/api/v1/admin/terminals").json()) == 1
    response = client.post("/api/v1/admin/terminals", json={**payload, "code": "CLOCK-C", "external_device_id": "CLOCK-C", "action_codes": []})
    assert response.status_code == 409
    assert client.post("/api/v1/admin/terminals", json={**payload, "code": "DRAFT", "external_device_id": "DRAFT", "active": False, "action_codes": []}).status_code == 201


def test_terminal_activation_binds_browser_and_hides_code_from_runtime_api(monitor):
    client, db = monitor
    terminal, _ = configured_terminal(client)
    assert client.get("/api/v1/terminal/config").status_code == 401
    activate_created_terminal(client, terminal)
    config = client.get("/api/v1/terminal/config")
    assert config.status_code == 200
    assert config.json()["code"] == "CLOCK-A"
    listed = client.get("/api/v1/admin/terminals").json()[0]
    assert listed["provisioned"] is True
    assert listed["activation_pending"] is False
    assert listed["activation_token"] is None


def test_edit_configuration_keeps_captured_event_snapshot(monitor):
    client, db = monitor
    terminal, payload = configured_terminal(client)
    activate_created_terminal(client, terminal)
    response = client.post("/api/v1/terminal/scan", json={"reporter_id": "0001", "identification_method": "KEYPAD"})
    assert response.status_code == 200
    event_id = response.json()["event"]["id"]
    action = next(row for row in client.get("/api/v1/admin/actions").json() if row["code"] == "START")
    action.update(label="Start shift", supplier_device_event="BSS_NEW_START", oracle_attributes={"Reason":"START"})
    assert client.put("/api/v1/admin/actions/START", json=action).status_code == 200
    response = client.put("/api/v1/admin/terminals/CLOCK-A", json={
        **payload,
        "name": "Updated gate",
        "external_device_id": "NEW-DEVICE",
        "identification_mode": "KEYPAD",
        "reporter_id_type": "PERSON",
        "oracle_attributes": {"Workshop": "Finishing", "Project": "P99"},
    })
    assert response.status_code == 200
    assert response.json()["name"] == "Updated gate"
    db.expire_all()
    event = db.get(TimeEvent, event_id)
    assert event.device_id == "CLOCK-A"
    assert event.action_label == "Start"
    assert event.supplier_device_event == "BSS_START"
    assert event.reporter_id_type == "BADGE"
    assert event.oracle_attributes == {"Workshop": "Assembly", "Project": "P42"}
    config = client.get("/api/v1/terminal/config").json()
    assert config["actions"][0]["label"] == "Start shift"


def test_terminal_and_action_oracle_attributes_are_merged_for_new_events(monitor):
    client, db = monitor
    create_action(client, "START", "ENTER", {"EventClass": "WORK"})
    create_action(client, "STOP")
    payload = {
        "code": "CELL-07",
        "name": "Cell 07",
        "external_device_id": "CELL-07",
        "identification_mode": "KEYPAD",
        "reporter_id_type": "BADGE",
        "oracle_attributes": {"Workshop": "Extrusion", "Project": "P42", "Cell": "EX07"},
        "active": True,
        "action_codes": ["START", "STOP"],
    }
    terminal = client.post("/api/v1/admin/terminals", json=payload).json()
    activate_created_terminal(client, terminal)
    response = client.post("/api/v1/terminal/scan", json={"reporter_id": "0042", "identification_method": "KEYPAD"})
    assert response.status_code == 200
    event = db.get(TimeEvent, response.json()["event"]["id"])
    assert event.oracle_attributes == {
        "Workshop": "Extrusion",
        "Project": "P42",
        "Cell": "EX07",
        "EventClass": "WORK",
    }


def test_action_edits_cannot_break_active_terminal(monitor):
    client, db = monitor
    configured_terminal(client)
    action = next(row for row in client.get("/api/v1/admin/actions").json() if row["code"] == "START")
    assert client.put("/api/v1/admin/actions/START", json={**action, "active":False}).status_code == 409
    assert client.put("/api/v1/admin/actions/START", json={**action, "state_effect":"EXIT"}).status_code == 409
    result = next(row for row in client.get("/api/v1/admin/actions").json() if row["code"] == "START")
    assert result["active"] is True
    assert result["state_effect"] == "ENTER"
    create_action(client,"OTHER_START","ENTER")
    assert client.put("/api/v1/admin/terminals/CLOCK-A/actions",json={"action_codes":["START","STOP","OTHER_START"]}).status_code == 409


def test_new_and_edited_action_mapping_is_validated(monitor):
    client, db = monitor
    action = create_action(client, "MEAL")
    assert client.post("/api/v1/admin/actions", json={**action, "code":"LUNCH"}).status_code == 409
    response = client.put("/api/v1/admin/actions/MEAL", json={**action,"label":"Meal break","display_order":25,"oracle_attributes":{"reason":"MEAL"}})
    assert response.status_code == 200
    assert response.json()["oracle_attributes"] == {"reason":"MEAL"}
    assert client.put("/api/v1/admin/actions/MEAL", json={**action,"label":"  "}).status_code == 422
    assert client.put("/api/v1/admin/actions/MEAL", json={**action,"display_order":-1}).status_code == 422


def test_retry_requires_reconciliation_for_unknown_and_rejected(monitor):
    client, db = monitor
    event = TimeEvent(
        id="retry-test", request_number="BSS-retry-test", terminal_id=1, action_id=1,
        terminal_code="A", device_id="A", action_code="START", action_label="Start",
        supplier_device_event="BSS_START", state_effect="ENTER", reporter_id="1",
        reporter_id_type="BADGE", identification_method="KEYPAD",
        event_datetime=datetime.now(timezone.utc), event_timezone="Europe/Madrid",
        oracle_attributes={}, delivery_status="UNKNOWN",
    )
    db.add(event)
    db.commit()
    response = client.post("/api/v1/admin/events/retry-test/retry")
    assert response.status_code == 409
    assert "reconciliation" in response.json()["detail"]
    event.delivery_status = "REJECTED"
    db.commit()
    assert client.post("/api/v1/admin/events/retry-test/retry").status_code == 409


def test_bootstrap_does_not_replace_saved_assignments(monitor, monkeypatch):
    client, db = monitor
    from app import bootstrap
    monkeypatch.setattr(bootstrap.settings, "app_seed_defaults", True)
    monkeypatch.setattr(bootstrap, "SessionLocal", lambda: db)
    bootstrap.bootstrap()
    terminal = db.scalar(select(Terminal).where(Terminal.code == "DEMO-01"))
    terminal.actions = [action for action in terminal.actions if action.code != "BREAK"]
    db.commit()
    bootstrap.bootstrap()
    terminal = db.scalar(select(Terminal).where(Terminal.code == "DEMO-01"))
    assert "BREAK" not in [action.code for action in terminal.actions]
