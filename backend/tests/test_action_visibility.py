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


def test_hidden_assigned_exit_is_internal_only_and_cascade_works(monitor):
    from app.domain.enums import IdentificationMethod
    from app.services.event_service import scan, record_exit
    from app.models.terminal import Terminal
    from app.models.action import Action
    from app.models.time_event import TimeEvent
    from app.models.perimeter import FactoryPerimeterEvent
    from sqlalchemy import select
    from fastapi import HTTPException
    import pytest
    client, db = monitor
    terminal, payload = configured_terminal(client)
    hidden = create_action(client, 'AUTO_GATE')
    assert client.put('/api/v1/admin/actions/AUTO_GATE', json={**hidden,'show_on_terminal':False}).status_code == 200
    cell = db.scalar(select(Terminal).where(Terminal.code=='CLOCK-A'))
    cell.actions.append(db.scalar(select(Action).where(Action.code=='AUTO_GATE')))
    gate = Terminal(code='GATE',name='Gate',external_device_id='GATE',terminal_role='PERIMETER_ENTER')
    db.add(gate); db.commit()
    assert client.put('/api/v1/admin/perimeter/DEFAULT',json={'enabled':True,'auto_exit_action_code':'AUTO_GATE','dedup_enabled':True,'dedup_seconds':5}).status_code==200
    assert scan(db,'GATE','000-test',IdentificationMethod.RFID).flow=='FACTORY_ENTRY_RECORDED'
    assert scan(db,'CLOCK-A','000-test',IdentificationMethod.RFID).flow=='ENTRY_RECORDED'
    activate_created_terminal(client,terminal)
    assert 'AUTO_GATE' not in [a['code'] for a in client.get('/api/v1/terminal/config').json()['actions']]
    with pytest.raises(HTTPException):
        record_exit(db,'CLOCK-A','000-test',IdentificationMethod.RFID,'AUTO_GATE')
    db.rollback()
    gate.terminal_role='PERIMETER_EXIT';db.commit()
    assert scan(db,'GATE','000-test',IdentificationMethod.RFID).flow=='FACTORY_EXIT_RECORDED'
    exit_event=db.scalar(select(TimeEvent).where(TimeEvent.state_effect=='EXIT'))
    movement=db.scalar(select(FactoryPerimeterEvent).where(FactoryPerimeterEvent.direction=='EXIT'))
    assert exit_event.action_code=='AUTO_GATE' and exit_event.delivery_status=='PENDING'
    assert movement.auto_cell_exit_event_id==exit_event.id
    assert movement.correlation_id==exit_event.correlation_id
    assert movement.event_datetime==exit_event.event_datetime


def test_cannot_hide_only_entry_or_last_required_subaction(monitor):
    client, db = monitor
    configured_terminal(client)
    action=next(a for a in client.get('/api/v1/admin/actions').json() if a['code']=='START')
    assert client.put('/api/v1/admin/actions/START',json={**action,'show_on_terminal':False}).status_code==409
