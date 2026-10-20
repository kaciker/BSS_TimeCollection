"""Hidden operational actions and perimeter action selection."""
from test_monitoring import monitor
from test_configuration import configured_terminal, create_action, activate_created_terminal


def test_hidden_action_is_available_to_perimeter_but_not_worker(monitor):
    client, db = monitor
    terminal, _ = configured_terminal(client)
    result = client.post("/api/v1/admin/actions", json={
        "code": "AUTO_GATE_EXIT", "label": "Automatic factory exit",
        "supplier_device_event": "BSS_AUTO_GATE_EXIT", "state_effect": "EXIT",
        "display_order": 500, "oracle_attributes": {}, "active": True,
        "show_on_terminal": False, "requires_subaction": False,
    })
    assert result.status_code == 201, result.text
    assert result.json()["show_on_terminal"] is False
    actions = client.get("/api/v1/admin/actions").json()
    assert next(a for a in actions if a["code"] == "AUTO_GATE_EXIT")["show_on_terminal"] is False
    assert client.put("/api/v1/admin/perimeter/DEFAULT", json={
        "enabled": True, "badge_source": "OPEN", "dedup_enabled": True,
        "dedup_seconds": 5, "auto_exit_action_code": "AUTO_GATE_EXIT",
    }).status_code == 200
    activate_created_terminal(client, terminal)
    assert "AUTO_GATE_EXIT" not in [a["code"] for a in client.get("/api/v1/terminal/config").json()["actions"]]


def test_cannot_hide_last_visible_terminal_exit(monitor):
    client, db = monitor
    configured_terminal(client)
    action = next(a for a in client.get("/api/v1/admin/actions").json() if a["code"] == "STOP")
    response = client.put("/api/v1/admin/actions/STOP", json={**action, "show_on_terminal": False})
    assert response.status_code == 409
    assert next(a for a in client.get("/api/v1/admin/actions").json() if a["code"] == "STOP")["show_on_terminal"] is True


def test_legacy_actions_default_visible(monitor):
    client, db = monitor
    action = create_action(client, "MEAL")
    assert action["show_on_terminal"] is True
