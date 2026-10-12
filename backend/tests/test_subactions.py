from test_configuration import activate_created_terminal, configured_terminal, create_action
from test_monitoring import monitor


def test_exit_action_can_open_one_level_of_subactions(monitor):
    client, _ = monitor
    terminal, payload = configured_terminal(client)
    parent = client.post("/api/v1/admin/actions", json={
        "code": "FACTORY_EXIT",
        "label": "Factory exit",
        "supplier_device_event": "BSS_FACTORY_EXIT_MENU",
        "state_effect": "EXIT",
        "display_order": 20,
        "oracle_attributes": {},
        "requires_subaction": True,
    })
    assert parent.status_code == 201, parent.text
    for code, label in [("PERSONAL_MATTERS", "Personal matters"), ("MEDICAL", "Medical"), ("LEGAL_MATTERS", "Legal matters")]:
        response = client.post("/api/v1/admin/actions", json={
            "code": code,
            "label": label,
            "supplier_device_event": f"BSS_{code}",
            "state_effect": "EXIT",
            "display_order": 30,
            "oracle_attributes": {},
            "parent_action_code": "FACTORY_EXIT",
        })
        assert response.status_code == 201, response.text

    action_codes = payload["action_codes"] + ["FACTORY_EXIT", "PERSONAL_MATTERS", "MEDICAL", "LEGAL_MATTERS"]
    assert client.put("/api/v1/admin/terminals/CLOCK-A/actions", json={"action_codes": action_codes}).status_code == 200
    activate_created_terminal(client, terminal)
    assert client.post("/api/v1/terminal/scan", json={"reporter_id":"42","identification_method":"KEYPAD"}).json()["flow"] == "ENTRY_RECORDED"
    first = client.post("/api/v1/terminal/scan", json={"reporter_id":"42","identification_method":"KEYPAD"}).json()
    assert first["flow"] == "EXIT_REQUIRED"
    factory = next(action for action in first["actions"] if action["code"] == "FACTORY_EXIT")
    assert factory["has_subactions"] is True
    second = client.post("/api/v1/terminal/exit", json={"reporter_id":"42","identification_method":"KEYPAD","action_code":"FACTORY_EXIT"}).json()
    assert second["flow"] == "SUBACTION_REQUIRED"
    assert {item["label"] for item in second["actions"]} == {"Personal matters", "Medical", "Legal matters"}
    final = client.post("/api/v1/terminal/exit", json={"reporter_id":"42","identification_method":"KEYPAD","action_code":"MEDICAL"}).json()
    assert final["flow"] == "EXIT_RECORDED"
    assert final["event"]["action_code"] == "MEDICAL"


def test_subactions_require_parent_and_terminal_assignment(monitor):
    client, _ = monitor
    configured_terminal(client)
    create_action(client, "OTHER", "EXIT")
    invalid = client.post("/api/v1/admin/actions", json={
        "code": "CHILD",
        "label": "Child",
        "supplier_device_event": "BSS_CHILD",
        "state_effect": "EXIT",
        "display_order": 30,
        "oracle_attributes": {},
        "parent_action_code": "OTHER",
    })
    assert invalid.status_code == 409
