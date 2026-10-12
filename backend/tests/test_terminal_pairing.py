from test_configuration import configured_terminal
from test_monitoring import monitor


def test_browser_pairing_code_binds_terminal_without_activation_link(monitor):
    client, db = monitor
    terminal, _ = configured_terminal(client)
    assert client.get("/api/v1/terminal/config").status_code == 401

    started = client.post("/api/v1/terminal/pairing")
    assert started.status_code == 201, started.text
    pairing = started.json()
    assert len(pairing["pairing_code"]) == 9
    assert pairing["pairing_code"][4] == "-"
    assert len(pairing["request_token"]) >= 32

    waiting = client.post("/api/v1/terminal/pairing/status", json={"request_token": pairing["request_token"]})
    assert waiting.status_code == 200
    assert waiting.json()["status"] == "WAITING"

    approved = client.post(
        "/api/v1/admin/terminals/CLOCK-A/pair",
        json={"pairing_code": pairing["pairing_code"].lower()},
    )
    assert approved.status_code == 200, approved.text

    completed = client.post("/api/v1/terminal/pairing/status", json={"request_token": pairing["request_token"]})
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "APPROVED"
    assert completed.json()["config"]["code"] == "CLOCK-A"
    assert "HttpOnly" in completed.headers["set-cookie"]
    assert client.get("/api/v1/terminal/config").json()["code"] == "CLOCK-A"

    # Pairing consumes any unused activation link and cannot be replayed.
    assert client.post("/api/v1/terminal/activate", json={"token": terminal["activation_token"]}).status_code == 404
    replay = client.post("/api/v1/terminal/pairing/status", json={"request_token": pairing["request_token"]})
    assert replay.status_code == 409


def test_pairing_code_is_single_use_and_rejects_unknown_codes(monitor):
    client, db = monitor
    configured_terminal(client)
    started = client.post("/api/v1/terminal/pairing").json()
    assert client.post("/api/v1/admin/terminals/CLOCK-A/pair", json={"pairing_code": "ABCD-EFGH"}).status_code == 404
    assert client.post("/api/v1/admin/terminals/CLOCK-A/pair", json={"pairing_code": started["pairing_code"]}).status_code == 200
    assert client.post("/api/v1/admin/terminals/CLOCK-A/pair", json={"pairing_code": started["pairing_code"]}).status_code == 409
