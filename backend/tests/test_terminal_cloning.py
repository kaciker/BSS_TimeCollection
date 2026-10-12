from sqlalchemy import select

from app.models.terminal import Terminal
from test_configuration import configured_terminal, activate_created_terminal
from test_monitoring import monitor


def test_clone_copies_settings_but_not_browser_identity_or_events(monitor):
    client, db = monitor
    terminal, payload = configured_terminal(client)
    activate_created_terminal(client, terminal)
    assert client.post("/api/v1/terminal/scan",json={"reporter_id":"CLONE-TEST","identification_method":"KEYPAD"}).status_code == 200
    response = client.post("/api/v1/admin/terminals/CLOCK-A/clone")
    assert response.status_code == 201
    clone = response.json()
    assert clone["code"] == "CLOCK-A-1"
    assert clone["external_device_id"] == "CLOCK-A-1"
    for field in ["identification_mode","reporter_id_type","oracle_attributes","active","action_codes"]:
        assert clone[field] == terminal[field]
    assert clone["provisioned"] is False
    assert clone["activation_pending"] is False
    assert clone["activation_token"] is None
    stored = db.scalar(select(Terminal).where(Terminal.code == clone["code"]))
    assert stored.activated_at is None
    assert stored.last_seen_at is None
    assert stored.last_ip is None
    assert stored.last_user_agent is None
    assert client.get("/api/v1/terminal/config").json()["code"] == "CLOCK-A"
    assert client.get("/api/v1/admin/monitoring/events?terminal_code=CLOCK-A-1").json()["total"] == 0
    edited = {**payload,"name":"Edited clone","oracle_attributes":{"Workshop":"New workshop"}}
    assert client.put("/api/v1/admin/terminals/CLOCK-A-1",json=edited | {"external_device_id":"CLOCK-A-1"}).status_code == 200
    original = next(row for row in client.get("/api/v1/admin/terminals").json() if row["code"] == "CLOCK-A")
    assert original["oracle_attributes"] == terminal["oracle_attributes"]


def test_clone_suffix_skips_conflicts_on_either_identifier(monitor):
    client, db = monitor
    _, payload = configured_terminal(client)
    assert client.post("/api/v1/admin/terminals",json={**payload,"code":"UNRELATED","external_device_id":"CLOCK-A-1"}).status_code == 201
    assert client.post("/api/v1/admin/terminals",json={**payload,"code":"CLOCK-A-2","external_device_id":"OTHER"}).status_code == 201
    first = client.post("/api/v1/admin/terminals/CLOCK-A/clone").json()
    second = client.post("/api/v1/admin/terminals/CLOCK-A/clone").json()
    assert first["code"] == first["external_device_id"] == "CLOCK-A-3"
    assert second["code"] == second["external_device_id"] == "CLOCK-A-4"
    assert client.post("/api/v1/admin/terminals/MISSING/clone").status_code == 404


def test_clone_reserves_suffix_space_at_maximum_field_lengths(monitor):
    client, db = monitor
    _, payload = configured_terminal(client)
    code, device = "C" * 64, "D" * 128
    assert client.post("/api/v1/admin/terminals",json={**payload,"code":code,"external_device_id":device,"name":"N"*160}).status_code == 201
    for index in [1,2]:
        response = client.post(f"/api/v1/admin/terminals/{code}/clone")
        assert response.status_code == 201
        clone = response.json()
        assert clone["code"] == "C" * 62 + f"-{index}"
        assert clone["external_device_id"] == "D" * 126 + f"-{index}"
        assert len(clone["name"]) == 160
