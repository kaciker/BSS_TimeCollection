import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import httpx
import pytest

from test_configuration import activate_created_terminal, configured_terminal
from test_monitoring import monitor


def test_activation_is_one_time_and_reprovisioning_revokes_session(monitor):
    client, db = monitor
    terminal, _ = configured_terminal(client)
    activated = client.post("/api/v1/terminal/activate", json={"token": terminal["activation_token"]})
    assert activated.status_code == 200
    assert "HttpOnly" in activated.headers["set-cookie"]
    assert "SameSite=strict" in activated.headers["set-cookie"]
    assert client.post("/api/v1/terminal/activate", json={"token": terminal["activation_token"]}).status_code == 404
    assert client.get("/api/v1/terminal/config").status_code == 200
    new_token = client.post("/api/v1/admin/terminals/CLOCK-A/provision").json()["activation_token"]
    assert client.get("/api/v1/terminal/config").status_code == 401
    assert client.post("/api/v1/terminal/activate", json={"token": new_token}).status_code == 200
    assert client.get("/api/v1/terminal/config").json()["code"] == "CLOCK-A"
    # URL codes cannot choose another identity; diagnostics are not identity.
    assert client.get("/api/v1/terminal/OTHER/config").status_code == 404
    assert client.get("/api/v1/terminal/config", headers={"User-Agent":"Different browser diagnostics"}).json()["code"] == "CLOCK-A"


@pytest.mark.skipif(not os.environ.get("IDENTITY_TEST_BASE_URL"), reason="Requires an isolated PostgreSQL-backed API")
def test_concurrent_activation_has_exactly_one_consumer():
    base = os.environ["IDENTITY_TEST_BASE_URL"]
    prefix = f"TEST-RACE-{uuid4().hex[:12]}"
    with httpx.Client(base_url=base, timeout=20) as client:
        for effect in ("ENTER", "EXIT"):
            code = f"{prefix}-{effect}"
            response = client.post("/api/v1/admin/actions", json={
                "code":code,"label":f"Test {effect.lower()}","supplier_device_event":code,"state_effect":effect,
            })
            assert response.status_code == 201, response.text
        response = client.post("/api/v1/admin/terminals", json={
            "code":prefix,"name":"Concurrent activation test","external_device_id":prefix,
            "action_codes":[f"{prefix}-ENTER",f"{prefix}-EXIT"],
        })
        assert response.status_code == 201, response.text
        for _ in range(5):
            provision = client.post(f"/api/v1/admin/terminals/{prefix}/provision")
            token = provision.json()["activation_token"]
            barrier = Barrier(8)
            def activate(index):
                with httpx.Client(base_url=base, timeout=20) as browser:
                    barrier.wait()
                    return browser.post("/api/v1/terminal/activate",json={"token":token}).status_code
            with ThreadPoolExecutor(max_workers=8) as pool:
                statuses = list(pool.map(activate, range(8)))
            assert statuses.count(200) == 1, statuses
            assert statuses.count(404) == 7, statuses
