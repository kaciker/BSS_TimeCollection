import pytest
from sqlalchemy import func, select

from app.models.exit_policy import policies
from app.models.time_event import TimeEvent
from app.models.transmission_attempt import TransmissionAttempt
from test_configuration import activate_created_terminal, configured_terminal
from test_monitoring import monitor

BASE = '/api/v1/admin/policies/same-terminal-exit'


def clocks(client):
    a, payload = configured_terminal(client)
    b = client.post('/api/v1/admin/terminals', json={**payload, 'code': 'CLOCK-B', 'external_device_id': 'CLOCK-B'}).json()
    return a, b


def scan(client, badge='policy-test'):
    return client.post('/api/v1/terminal/scan', json={'reporter_id': badge, 'identification_method': 'KEYPAD'})


def exit_badge(client, badge='policy-test'):
    return client.post('/api/v1/terminal/exit', json={'reporter_id': badge, 'identification_method': 'KEYPAD', 'action_code': 'STOP'})


def test_defaults_inheritance_override_and_validation(monitor):
    client, db = monitor
    clocks(client)
    assert client.get(BASE).json()['global_mode'] == 'DISABLED'
    assert db.scalar(select(func.count()).select_from(policies)) == 0
    assert client.put(BASE, json={'mode':'INHERIT'}).status_code == 422
    assert client.put(BASE, json={'mode':'UNKNOWN'}).status_code == 422
    assert client.put(BASE+'/terminals/MISSING', json={'mode':'DISABLED'}).status_code == 404
    for mode in ['SAME_TERMINAL', 'SAME_WORK_CELL', 'DISABLED']:
        assert client.put(BASE, json={'mode':mode}).status_code == 200
        assert all(t['effective_mode']==mode for t in client.get(BASE).json()['terminals'])
    client.put(BASE, json={'mode':'SAME_TERMINAL'})
    client.put(BASE+'/terminals/CLOCK-B', json={'mode':'DISABLED'})
    b = next(t for t in client.get(BASE).json()['terminals'] if t['code']=='CLOCK-B')
    assert b['effective_mode']=='DISABLED'
    client.put(BASE+'/terminals/CLOCK-B', json={'mode':'INHERIT'})
    b = next(t for t in client.get(BASE).json()['terminals'] if t['code']=='CLOCK-B')
    assert b['mode']=='INHERIT' and b['effective_mode']=='SAME_TERMINAL'
    assert db.scalar(select(func.count()).select_from(policies))==1


@pytest.mark.parametrize('mode,origin_cell,current_cell,same_terminal,allowed', [
    ('DISABLED',None,None,False,True),
    ('SAME_TERMINAL',None,None,True,True),
    ('SAME_TERMINAL',None,None,False,False),
    ('SAME_WORK_CELL','A','A',False,True),
    ('SAME_WORK_CELL','A','B',False,False),
    ('SAME_WORK_CELL',None,'A',False,False),
    ('SAME_WORK_CELL','A',None,False,False),
    ('SAME_WORK_CELL',None,None,True,False),
    ('SAME_WORK_CELL','A','a',False,False),
])
def test_capture_modes_and_rejected_exits_never_queue_oracle(monitor,mode,origin_cell,current_cell,same_terminal,allowed):
    client, db = monitor
    a,b = clocks(client)
    target = 'CLOCK-A' if same_terminal else 'CLOCK-B'
    client.put(BASE+'/terminals/CLOCK-A/work-cell',json={'work_cell':origin_cell or ''})
    client.put(BASE+f'/terminals/{target}/work-cell',json={'work_cell':current_cell or ''})
    client.put(BASE+f'/terminals/{target}',json={'mode':mode})
    activate_created_terminal(client,a)
    assert scan(client).json()['flow']=='ENTRY_RECORDED'
    if not same_terminal: activate_created_terminal(client,b)
    before = db.scalar(select(func.count()).select_from(TimeEvent))
    result=scan(client)
    assert result.status_code==(200 if allowed else 409),result.text
    result=exit_badge(client)
    assert result.status_code==(200 if allowed else 409),result.text
    if not allowed:
        assert 'No exit was recorded' in result.json()['detail']
        assert db.scalar(select(func.count()).select_from(TimeEvent))==before
        assert db.scalar(select(func.count()).select_from(TransmissionAttempt))==0
    else:
        assert result.json()['flow']=='EXIT_RECORDED'
        assert db.scalar(select(func.count()).select_from(TimeEvent))==before+1


def test_policy_rechecked_after_exit_menu_and_latest_entry(monitor):
    client, db=monitor
    a,b=clocks(client)
    activate_created_terminal(client,a)
    scan(client)
    activate_created_terminal(client,b)
    assert scan(client).json()['flow']=='EXIT_REQUIRED'
    client.put(BASE+'/terminals/CLOCK-B',json={'mode':'SAME_TERMINAL'})
    assert exit_badge(client).status_code==409
    client.put(BASE+'/terminals/CLOCK-B',json={'mode':'DISABLED'})
    assert exit_badge(client).status_code==200
    assert scan(client).json()['flow']=='ENTRY_RECORDED'
    client.put(BASE+'/terminals/CLOCK-B',json={'mode':'SAME_TERMINAL'})
    assert exit_badge(client).status_code==200


def test_work_cell_edit_preserves_attributes_and_validates_types(monitor):
    client, db=monitor
    _,payload=configured_terminal(client)
    for invalid in [True,17,[],{},'x'*65]:
        assert client.put(BASE+'/terminals/CLOCK-A/work-cell',json={'work_cell':invalid}).status_code==422
        assert client.put('/api/v1/admin/terminals/CLOCK-A',json={**payload,'oracle_attributes':{'work_cell':invalid}}).status_code==422
    assert client.put(BASE+'/terminals/CLOCK-A/work-cell',json={'work_cell':'  CELL-1  '}).json()['work_cell']=='CELL-1'
    attrs=client.get('/api/v1/admin/terminals').json()[0]['oracle_attributes']
    assert attrs=={**payload['oracle_attributes'],'work_cell':'CELL-1'}
    client.put(BASE+'/terminals/CLOCK-A/work-cell',json={'work_cell':''})
    assert client.get('/api/v1/admin/terminals').json()[0]['oracle_attributes']==payload['oracle_attributes']


def test_hierarchical_exit_rejection_has_no_event(monitor):
    client,db=monitor
    a,b=clocks(client)
    parent=client.post('/api/v1/admin/actions',json={'code':'FACTORY','label':'Factory','supplier_device_event':'FACTORY','state_effect':'EXIT','requires_subaction':True}).json()
    client.post('/api/v1/admin/actions',json={'code':'MEDICAL','label':'Medical','supplier_device_event':'MEDICAL','state_effect':'EXIT','parent_action_code':parent['code']})
    client.put('/api/v1/admin/terminals/CLOCK-B/actions',json={'action_codes':['START','STOP','FACTORY','MEDICAL']})
    activate_created_terminal(client,a);scan(client);activate_created_terminal(client,b)
    client.put(BASE+'/terminals/CLOCK-B',json={'mode':'SAME_TERMINAL'})
    for action in ['FACTORY','MEDICAL']:
        result=client.post('/api/v1/terminal/exit',json={'reporter_id':'policy-test','identification_method':'KEYPAD','action_code':action})
        assert result.status_code==409
    assert db.scalar(select(func.count()).select_from(TimeEvent))==1
    assert db.scalar(select(func.count()).select_from(TransmissionAttempt))==0


def test_terminal_options_save_policy_with_configuration_and_preserve_legacy_clients(monitor):
    client, db=monitor
    terminal,payload=configured_terminal(client)
    assert terminal['exit_policy_mode']=='INHERIT'
    assert terminal['global_exit_policy_mode']=='DISABLED'
    changed={**payload,'name':'Policy workstation','oracle_attributes':{**payload['oracle_attributes'],'work_cell':'CELL-X'},'exit_policy_mode':'SAME_WORK_CELL'}
    saved=client.put('/api/v1/admin/terminals/CLOCK-A',json=changed)
    assert saved.status_code==200,saved.text
    assert saved.json()['effective_exit_policy_mode']=='SAME_WORK_CELL'
    assert saved.json()['oracle_attributes']['work_cell']=='CELL-X'
    old_client=client.put('/api/v1/admin/terminals/CLOCK-A',json=payload)
    assert old_client.json()['exit_policy_mode']=='SAME_WORK_CELL'
    inherited=client.put('/api/v1/admin/terminals/CLOCK-A',json={**payload,'exit_policy_mode':'INHERIT'})
    assert inherited.json()['exit_policy_mode']=='INHERIT'
    assert inherited.json()['effective_exit_policy_mode']=='DISABLED'
    assert client.get(BASE).json()['global_mode']=='DISABLED'
    created=client.post('/api/v1/admin/terminals',json={**changed,'code':'CLOCK-C','external_device_id':'CLOCK-C','exit_policy_mode':'SAME_TERMINAL'})
    assert created.status_code==201,created.text
    assert created.json()['exit_policy_mode']=='SAME_TERMINAL'
    assert created.json()['effective_exit_policy_mode']=='SAME_TERMINAL'


def test_invalid_terminal_options_cannot_change_policy_or_configuration(monitor):
    client,db=monitor
    terminal,payload=configured_terminal(client)
    for invalid in [{'exit_policy_mode':'UNKNOWN'},{'action_codes':['MISSING'],'exit_policy_mode':'SAME_TERMINAL'},{'oracle_attributes':{'work_cell':False},'exit_policy_mode':'SAME_WORK_CELL'}]:
        response=client.put('/api/v1/admin/terminals/CLOCK-A',json={**payload,'name':'Must not save',**invalid})
        assert response.status_code in [400,422]
        current=client.get('/api/v1/admin/terminals').json()[0]
        assert current['name']==payload['name']
        assert current['oracle_attributes']==payload['oracle_attributes']
        assert current['exit_policy_mode']=='INHERIT'
