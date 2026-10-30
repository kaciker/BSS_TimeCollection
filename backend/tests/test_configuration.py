from datetime import datetime, timezone

from sqlalchemy import select

from test_monitoring import monitor
from app.core.config import settings
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
    workshop = client.post("/api/v1/admin/structure/workshops", json={"code":"TEST-W","description":"Test Workshop"}).json()
    subworkshop = client.post("/api/v1/admin/structure/subworkshops", json={"workshop_id":workshop["id"],"code":"TEST-S","description":"Test Subworkshop"}).json()
    project = client.post("/api/v1/admin/structure/project-lines", json={"subworkshop_id":subworkshop["id"],"code":"TEST-P","description":"Test Project"}).json()
    payload = {
        "code": code,
        "name": "North gate",
        "external_device_id": code,
        "identification_mode": "BOTH",
        "reporter_id_type": "BADGE",
        "oracle_attributes": {"Workshop": "Assembly", "Project": "P42"},
        "active": True,
        "project_line_id": project["id"],
        "workshop_id": workshop["id"],
        "subworkshop_id": subworkshop["id"],
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
    assert terminal["exit_menu_timeout_seconds"] == 5
    custom = client.post("/api/v1/admin/terminals", json={**payload, "code": "CLOCK-CUSTOM", "external_device_id": "CLOCK-CUSTOM", "exit_menu_timeout_seconds": 120, "active": False})
    assert custom.status_code == 201, custom.text
    assert custom.json()["exit_menu_timeout_seconds"] == 120
    response = client.post("/api/v1/admin/terminals", json={**payload, "code": "CLOCK-B"})
    assert response.status_code == 409
    assert "device ID" in response.json()["detail"]
    assert len(client.get("/api/v1/admin/terminals").json()) == 2
    response = client.post("/api/v1/admin/terminals", json={**payload, "code": "CLOCK-C", "external_device_id": "CLOCK-C", "action_codes": []})
    assert response.status_code == 409
    assert client.post("/api/v1/admin/terminals", json={**payload, "code": "DRAFT", "external_device_id": "DRAFT", "active": False, "action_codes": []}).status_code == 201


def test_terminal_code_is_allocated_and_retired_codes_are_not_reused(monitor):
    client, db = monitor
    _, payload = configured_terminal(client)
    automatic_payload = {key: value for key, value in payload.items() if key != "code"}
    first = client.post("/api/v1/admin/terminals", json={**automatic_payload, "external_device_id": "AUTO-DEVICE-1"})
    assert first.status_code == 201, first.text
    assert first.json()["code"] == "T0001"
    assert client.delete("/api/v1/admin/terminals/T0001").status_code == 200
    second = client.post("/api/v1/admin/terminals", json={**automatic_payload, "external_device_id": "AUTO-DEVICE-2"})
    assert second.status_code == 201, second.text
    assert second.json()["code"] == "T0002"


def test_reporter_id_type_is_global_integration_configuration(monitor, monkeypatch):
    client, db = monitor
    monkeypatch.setattr(settings, "oracle_person_reporter_id_type", "PERSON")
    terminal, _ = configured_terminal(client)
    assert terminal["reporter_id_type"] == "PERSON"
    integration = client.get("/api/v1/admin/integration-settings")
    assert integration.status_code == 200
    assert integration.json()["reporter_id_type"] == "PERSON"
    activate_created_terminal(client, terminal)
    response = client.post("/api/v1/terminal/scan", json={"reporter_id": "0001", "identification_method": "KEYPAD"})
    assert response.status_code == 200
    event = db.get(TimeEvent, response.json()["event"]["id"])
    assert event.reporter_id_type == "BADGE"


def test_integration_settings_expose_effective_nonsecret_values(monitor):
    client, _ = monitor
    response = client.get("/api/v1/admin/integration-settings")
    assert response.status_code == 200
    value = response.json()
    assert value["base_url"] == "https://fa-eocc-dev2-saasfaprod1.fa.ocs.oraclecloud.com"
    assert value["api_path"] == "/hcmRestApi/resources/11.13.18.05/timeEventRequests"
    assert value["oracle_source_id"] == "HUT_TCD_SUPP1"
    assert value["auth_mode"] == "basic"
    assert value["reporter_id_type"] == "PERSON"
    assert value["rest_framework_version"] == "4"
    assert value["oracle_enabled"] is False
    assert value["password"] in {"Configured", "Not configured"}
    assert value["bearer_token"] in {"Configured", "Not configured"}


def test_connection_test_only_checks_base_https_host(monitor, monkeypatch):
    import app.routers.admin as admin
    client, _ = monitor
    called = {}
    class Response:
        status_code = 401
    def fake_get(url, **kwargs):
        called.update(url=url, kwargs=kwargs)
        return Response()
    monkeypatch.setattr(admin.httpx, "get", fake_get)
    result = client.post("/api/v1/admin/integration-connection-test", json={}).json()
    assert called["url"] == settings.oracle_base_url
    assert result["reachable"] is True
    assert result["authentication_validated"] is False
    assert "timeEventRequests" not in called["url"]


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
    assert response.json()["reporter_id_type"] == "PERSON"
    db.expire_all()
    event = db.get(TimeEvent, event_id)
    assert event.device_id == "CLOCK-A"
    assert event.action_label == "Start"
    assert event.supplier_device_event == "BSS_START"
    assert event.oracle_supplier_event == "HUT_TCD_SUPP1_IN_2"
    assert event.reporter_id_type == "BADGE"
    assert event.oracle_attributes == {"Workshop": "Assembly", "Project": "P42"}
    config = client.get("/api/v1/terminal/config").json()
    assert config["actions"][0]["label"] == "Start shift"


def test_exit_menu_timeout_is_bounded_and_preserved_when_omitted(monitor):
    client, _ = monitor
    terminal, payload = configured_terminal(client)
    assert terminal["exit_menu_timeout_seconds"] == 5
    for invalid in (-1, 121):
        response = client.put("/api/v1/admin/terminals/CLOCK-A", json={**payload, "exit_menu_timeout_seconds": invalid})
        assert response.status_code == 422
    configured = client.put("/api/v1/admin/terminals/CLOCK-A", json={**payload, "exit_menu_timeout_seconds": 120})
    assert configured.status_code == 200
    assert configured.json()["exit_menu_timeout_seconds"] == 120
    unchanged = client.put("/api/v1/admin/terminals/CLOCK-A", json=payload)
    assert unchanged.status_code == 200
    assert unchanged.json()["exit_menu_timeout_seconds"] == 120
    disabled = client.put("/api/v1/admin/terminals/CLOCK-A", json={**payload, "exit_menu_timeout_seconds": 0})
    assert disabled.status_code == 200
    assert disabled.json()["exit_menu_timeout_seconds"] == 0


def test_terminal_and_action_oracle_attributes_are_merged_for_new_events(monitor):
    client, db = monitor
    create_action(client, "START", "ENTER", {"EventClass": "WORK"})
    create_action(client, "STOP")
    workshop = client.post("/api/v1/admin/structure/workshops", json={"code":"CELL-W","description":"Cell Workshop"}).json()
    subworkshop = client.post("/api/v1/admin/structure/subworkshops", json={"workshop_id":workshop["id"],"code":"CELL-S","description":"Cell Subworkshop"}).json()
    project = client.post("/api/v1/admin/structure/project-lines", json={"subworkshop_id":subworkshop["id"],"code":"CELL-P","description":"Cell Project"}).json()
    payload = {
        "code": "CELL-07",
        "name": "Cell 07",
        "external_device_id": "CELL-07",
        "identification_mode": "KEYPAD",
        "reporter_id_type": "BADGE",
        "oracle_attributes": {"Workshop": "Extrusion", "Project": "P42", "Cell": "EX07", "work_cell": "LOCAL-07"},
        "workshop_id": workshop["id"], "subworkshop_id": subworkshop["id"], "project_line_id": project["id"],
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
    assert client.put("/api/v1/admin/actions/START", json={**action, "state_effect":"EXIT"}).status_code == 422
    result = next(row for row in client.get("/api/v1/admin/actions").json() if row["code"] == "START")
    assert result["active"] is True
    assert result["state_effect"] == "ENTER"
    create_action(client,"OTHER_START","ENTER")
    assert client.put("/api/v1/admin/terminals/CLOCK-A/actions",json={"action_codes":["START","STOP","OTHER_START"]}).status_code == 409


def test_new_and_edited_action_mapping_is_validated(monitor):
    client, db = monitor
    action = create_action(client, "MEAL")
    assert client.post("/api/v1/admin/actions", json={**action, "code":"LUNCH"}).status_code == 201
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
