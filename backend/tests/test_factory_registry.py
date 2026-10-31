from app.models.factory import Factory, InstallationSettings
from app.models.terminal import Terminal
from sqlalchemy.orm import Session
from test_monitoring import monitor


def test_factory_registry_crud_and_persisted_default(monitor):
    client, db = monitor
    factories = client.get("/api/v1/admin/factories")
    assert factories.status_code == 200
    assert {item["code"] for item in factories.json()} == {"ARGANDA", "OTHER"}

    created = client.post("/api/v1/admin/factories", json={
        "code": "PLANT-2", "name": "Plant Two", "location": "Site 2",
        "country": "Spain", "timezone": "Europe/Madrid",
    })
    assert created.status_code == 201, created.text
    row = created.json()
    assert client.put(f"/api/v1/admin/factories/{row['id']}", json={"name": "Plant Two Updated"}).json()["name"] == "Plant Two Updated"
    assert client.put(f"/api/v1/admin/factories/{row['id']}", json={"code": "PLANT-3"}).status_code == 422
    assert client.put("/api/v1/admin/installation-settings/default-factory", json={"factory_code": "ARGANDA"}).status_code == 200
    with Session(db.get_bind()) as restarted_session:
        assert restarted_session.get(InstallationSettings, 1).default_factory_code == "ARGANDA"
    assert client.get("/api/v1/admin/installation-settings").json()["default_factory_code"] == "ARGANDA"


def test_terminal_factory_is_required_and_registry_validated(monitor):
    client, db = monitor
    missing = client.post("/api/v1/admin/terminals", json={"name": "Gate", "perimeter_only": True})
    unknown = client.post("/api/v1/admin/terminals", json={"name": "Gate", "factory_code": "NOT-REGISTERED", "perimeter_only": True})
    assert missing.status_code == 422
    assert unknown.status_code == 422

    created = client.post("/api/v1/admin/terminals", json={
        "name": "Arganda test gate", "factory_code": "ARGANDA", "perimeter_only": True,
    })
    assert created.status_code == 201, created.text
    assert created.json()["factory_code"] == "ARGANDA"
    assert db.scalar(__import__("sqlalchemy").select(Terminal).where(Terminal.code == created.json()["code"])).factory_code == "ARGANDA"
    assert client.put(f"/api/v1/admin/perimeter/terminals/{created.json()['code']}/role", json={"factory_code": "UNKNOWN", "role": "PERIMETER_ENTER"}).status_code == 422


def test_factory_perimeter_settings_are_isolated_by_registry_code(monitor):
    client, _ = monitor
    action = client.post("/api/v1/admin/actions", json={"code":"EXIT-AUTO","label":"Exit","supplier_device_event":"BSS_EXIT_AUTO","state_effect":"EXIT","display_order":10}).json()
    arganda = client.put("/api/v1/admin/perimeter/ARGANDA", json={"enabled": True, "auto_exit_action_code": action["code"], "dedup_enabled": True, "dedup_seconds": 9})
    other = client.put("/api/v1/admin/perimeter/OTHER", json={"enabled": False, "dedup_enabled": False, "dedup_seconds": 2})
    assert arganda.status_code == 200 and other.status_code == 200
    assert client.get("/api/v1/admin/perimeter/ARGANDA").json()["dedup_seconds"] == 9
    assert client.get("/api/v1/admin/perimeter/OTHER").json()["dedup_seconds"] == 2
    assert client.get("/api/v1/admin/perimeter/UNKNOWN").status_code == 422


def test_inactive_factory_cannot_become_default_or_terminal_assignment(monitor):
    client, db = monitor
    factory = db.scalar(__import__("sqlalchemy").select(Factory).where(Factory.code == "OTHER"))
    factory.active = False
    db.commit()
    assert client.put("/api/v1/admin/installation-settings/default-factory", json={"factory_code": "OTHER"}).status_code == 422
    assert client.post("/api/v1/admin/terminals", json={"name": "Inactive", "factory_code": "OTHER", "perimeter_only": True}).status_code == 422
