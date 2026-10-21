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
    assert client.put("/api/v1/admin/perimeter/terminals/GATE/role", json={"factory_code": "DEFAULT", "role": "PERIMETER_EXIT"}).status_code == 200
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
    assert movements[-1].correlation_id == events[-1].correlation_id
    assert movements[-1].event_datetime == events[-1].event_datetime
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


def test_bidirectional_repeated_reads_do_not_toggle_presence(monitor):
    client, db = monitor
    _, gate = setup_factory(client)
    activate_created_terminal(client, gate)
    assert scan(client, "00001234").json()["flow"] == "FACTORY_ENTRY_RECORDED"
    assert scan(client, "00001234").json()["flow"] == "DUPLICATE_IGNORED"
    assert client.get("/api/v1/admin/perimeter/DEFAULT/presence").json()["inside"] == ["00001234"]
    assert len(db.scalars(select(FactoryPerimeterEvent)).all()) == 1


def test_cascade_preserves_entry_snapshots_after_cell_configuration_change(monitor):
    from app.models.terminal import Terminal
    client, db = monitor
    _, gate = setup_factory(client)
    activate_created_terminal(client, gate)
    assert scan(client).json()["flow"] == "FACTORY_ENTRY_RECORDED"
    token = client.post('/api/v1/admin/terminals/CLOCK-A/provision').json()['activation_token']
    client.post('/api/v1/terminal/activate', json={'token': token})
    assert scan(client).json()["flow"] == "ENTRY_RECORDED"
    entry = db.scalar(select(TimeEvent))
    cell = db.scalar(select(Terminal).where(Terminal.code == "CLOCK-A"))
    cell.external_device_id = "CHANGED"
    cell.oracle_attributes = {"Workshop": "Changed"}
    cell.project_line.active = False
    db.commit()
    client.put("/api/v1/admin/perimeter/terminals/GATE/role", json={"factory_code": "DEFAULT", "role": "PERIMETER_EXIT"})
    token = client.post('/api/v1/admin/terminals/GATE/provision').json()['activation_token']
    client.post('/api/v1/terminal/activate', json={'token': token})
    assert scan(client).json()["flow"] == "FACTORY_EXIT_RECORDED"
    leave = db.scalar(select(TimeEvent).where(TimeEvent.state_effect == "EXIT"))
    assert leave.device_id == entry.device_id
    assert leave.oracle_attributes == entry.oracle_attributes
    assert leave.project_line_code == entry.project_line_code


def test_cascade_commit_failure_rolls_back_both_movements(monitor, monkeypatch):
    from sqlalchemy.orm import Session
    from app.services.event_service import scan as capture
    from app.domain.enums import IdentificationMethod
    import pytest
    client, db = monitor
    _, gate = setup_factory(client)
    activate_created_terminal(client, gate)
    scan(client)
    capture(db, 'CLOCK-A', 'RFID-0001', IdentificationMethod.KEYPAD)
    client.put("/api/v1/admin/perimeter/terminals/GATE/role", json={"factory_code": "DEFAULT", "role": "PERIMETER_EXIT"})
    def fail():
        raise RuntimeError("simulated commit failure")
    with monkeypatch.context() as patch:
        patch.setattr(db, "commit", fail)
        with pytest.raises(RuntimeError):
            capture(db, 'GATE', 'RFID-0001', IdentificationMethod.KEYPAD)
        db.rollback()
    assert len(db.scalars(select(TimeEvent)).all()) == 1
    assert len(db.scalars(select(FactoryPerimeterEvent)).all()) == 1


def test_cell_duplicates_and_other_terminal_do_not_block_exit(monitor):
    from app.services.event_service import scan as capture, record_exit
    from app.domain.enums import IdentificationMethod as Method
    client, db = monitor
    _, gate = setup_factory(client)
    activate_created_terminal(client, gate)
    scan(client)
    assert capture(db, 'CLOCK-A', 'RFID-0001', Method.RFID).flow == 'ENTRY_RECORDED'
    assert capture(db, 'CLOCK-A', 'RFID-0001', Method.RFID).flow == 'DUPLICATE_IGNORED'
    assert record_exit(db, 'CLOCK-A', 'RFID-0001', Method.RFID, 'STOP').flow == 'EXIT_RECORDED'
    assert record_exit(db, 'CLOCK-A', 'RFID-0001', Method.RFID, 'STOP').flow == 'DUPLICATE_IGNORED'
    assert len(db.scalars(select(TimeEvent)).all()) == 2


def test_disabled_perimeter_preserves_legacy_cell_capture(monitor):
    from app.services.event_service import scan as capture, record_exit
    from app.domain.enums import IdentificationMethod as Method
    client, db = monitor
    configured_terminal(client)
    assert client.get('/api/v1/admin/perimeter/DEFAULT').json()['enabled'] is False
    assert capture(db, 'CLOCK-A', 'legacy', Method.KEYPAD).flow == 'ENTRY_RECORDED'
    assert capture(db, 'CLOCK-A', 'legacy', Method.KEYPAD).flow == 'EXIT_REQUIRED'
    assert record_exit(db, 'CLOCK-A', 'legacy', Method.KEYPAD, 'STOP').flow == 'EXIT_RECORDED'
    assert len(db.scalars(select(FactoryPerimeterEvent)).all()) == 0


def test_factory_presence_isolated_and_external_source_fails_closed(monitor, monkeypatch):
    from app.models.perimeter import FactoryPerimeterSettings
    from app.services.event_service import scan as capture
    from app.domain.enums import IdentificationMethod as Method
    import pytest
    from fastapi import HTTPException
    client, db = monitor
    _, gate = setup_factory(client)
    activate_created_terminal(client, gate)
    scan(client, '0000')
    assert client.get('/api/v1/admin/perimeter/OTHER/presence').json()['inside'] == []
    config = db.get(FactoryPerimeterSettings, 'DEFAULT')
    config.badge_source = 'EXTERNAL'
    db.commit()
    from app.services import external_perimeter
    monkeypatch.setattr(
        external_perimeter,
        'check_external_presence',
        lambda badge: {'status': 'ERROR', 'event_time': None},
    )
    with pytest.raises(HTTPException) as error:
        capture(db, 'CLOCK-A', '0000', Method.RFID)
    assert error.value.status_code == 503
    db.rollback()
    assert len(db.scalars(select(TimeEvent)).all()) == 0


def test_external_connection_failure_does_not_block_cell_exit(monitor, monkeypatch):
    from app.models.perimeter import FactoryPerimeterSettings
    from app.services.event_service import scan as capture, record_exit
    from app.domain.enums import IdentificationMethod as Method
    client, db = monitor
    configured_terminal(client)
    assert capture(db, 'CLOCK-A', 'READONLY-EXIT', Method.KEYPAD).flow == 'ENTRY_RECORDED'
    db.add(FactoryPerimeterSettings(
        factory_code='DEFAULT', enabled=True, badge_source='EXTERNAL',
        dedup_enabled=False, dedup_seconds=0, auto_exit_action_code='STOP',
    ))
    db.commit()
    from app.services import external_perimeter
    monkeypatch.setattr(external_perimeter, 'check_external_presence', lambda badge: {'status': 'ERROR', 'event_time': None})
    result = record_exit(db, 'CLOCK-A', 'READONLY-EXIT', Method.KEYPAD, 'STOP')
    assert result.flow == 'EXIT_RECORDED'
    assert len(db.scalars(select(TimeEvent)).all()) == 2


def test_clone_preserves_factory_role_and_does_not_copy_identity(monitor):
    client, db = monitor
    _, gate = setup_factory(client)
    clone = client.post('/api/v1/admin/terminals/GATE/clone')
    assert clone.status_code == 201, clone.text
    assert clone.json()['factory_code'] == 'DEFAULT'
    assert clone.json()['terminal_role'] == 'PERIMETER_BOTH'
