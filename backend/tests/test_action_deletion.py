from app.models.perimeter import FactoryPerimeterSettings
from test_configuration import activate_created_terminal, configured_terminal, create_action
from test_monitoring import monitor


def test_unused_action_can_be_deleted(monitor):
    client, _ = monitor
    create_action(client, "TEMP_UNUSED")

    response = client.delete("/api/v1/admin/actions/TEMP_UNUSED")

    assert response.status_code == 200, response.text
    assert response.json()["detail"] == "Action TEMP_UNUSED deleted"
    assert all(action["code"] != "TEMP_UNUSED" for action in client.get("/api/v1/admin/actions").json())


def test_action_with_recorded_history_cannot_be_deleted(monitor):
    client, _ = monitor
    terminal, _ = configured_terminal(client)
    activate_created_terminal(client, terminal)
    scan = client.post("/api/v1/terminal/scan", json={"reporter_id": "0001", "identification_method": "KEYPAD"})
    assert scan.status_code == 200, scan.text

    response = client.delete("/api/v1/admin/actions/START")

    assert response.status_code == 409
    assert "recorded time events" in response.json()["detail"]
    assert "Deactivate it instead" in response.json()["detail"]
    assert any(action["code"] == "START" for action in client.get("/api/v1/admin/actions").json())


def test_parent_action_with_subactions_cannot_be_deleted(monitor):
    client, _ = monitor
    parent = client.post("/api/v1/admin/actions", json={
        "code": "PARENT_EXIT",
        "label": "Parent exit",
        "supplier_device_event": "BSS_PARENT_EXIT",
        "state_effect": "EXIT",
        "display_order": 10,
        "oracle_attributes": {},
        "requires_subaction": True,
    })
    assert parent.status_code == 201, parent.text
    child = client.post("/api/v1/admin/actions", json={
        "code": "CHILD_EXIT",
        "label": "Child exit",
        "supplier_device_event": "BSS_CHILD_EXIT",
        "state_effect": "EXIT",
        "display_order": 11,
        "oracle_attributes": {},
        "parent_action_code": "PARENT_EXIT",
    })
    assert child.status_code == 201, child.text

    response = client.delete("/api/v1/admin/actions/PARENT_EXIT")

    assert response.status_code == 409
    assert "parent of sub-action(s): CHILD_EXIT" in response.json()["detail"]


def test_auto_exit_action_cannot_be_deleted(monitor):
    client, db = monitor
    create_action(client, "AUTO_FACTORY_EXIT")
    db.add(FactoryPerimeterSettings(
        factory_code="ARGANDA",
        enabled=True,
        badge_source="OPEN",
        dedup_enabled=True,
        dedup_seconds=5,
        auto_exit_action_code="AUTO_FACTORY_EXIT",
    ))
    db.commit()

    response = client.delete("/api/v1/admin/actions/AUTO_FACTORY_EXIT")

    assert response.status_code == 409
    assert "automatic factory exit for: ARGANDA" in response.json()["detail"]
