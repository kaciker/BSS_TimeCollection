from test_monitoring import monitor
from test_configuration import configured_terminal, activate_created_terminal
from sqlalchemy import select
from app.models.time_event import TimeEvent
from app.models.perimeter import FactoryPerimeterEvent


def test_create_perimeter_without_cell_config_and_capture_uid_only(monitor):
    client, db = monitor
    configured_terminal(client)
    result=client.post('/api/v1/admin/terminals',json={'name':'Factory gate','perimeter_only':True,'identification_mode':'RFID'})
    assert result.status_code==201,result.text
    gate=result.json()
    assert gate['terminal_role']=='PERIMETER_BOTH'
    assert gate['project_line_id'] is None and gate['action_codes']==[]
    assert gate['oracle_attributes']=={} and gate['exit_policy_mode']=='DISABLED'
    assert len(gate['external_device_id'])<=40
    assert client.put('/api/v1/admin/perimeter/DEFAULT',json={'enabled':True,'auto_exit_action_code':'STOP','dedup_enabled':False}).status_code==200
    activate_created_terminal(client,gate)
    assert client.get('/api/v1/terminal/config').json()['actions']==[]
    for flow in ['FACTORY_ENTRY_RECORDED','FACTORY_EXIT_RECORDED']:
        result=client.post('/api/v1/terminal/scan',json={'reporter_id':'000-test','identification_method':'RFID'})
        assert result.json()['flow']==flow,result.text
    assert db.scalars(select(TimeEvent)).all()==[]
    assert len(db.scalars(select(FactoryPerimeterEvent)).all())==2
    clone=client.post(f"/api/v1/admin/terminals/{gate['code']}/clone")
    assert clone.status_code==201,clone.text
    assert clone.json()['terminal_role']=='PERIMETER_BOTH'
    assert clone.json()['action_codes']==[]
    update=client.put(f"/api/v1/admin/terminals/{gate['code']}",json={'name':'Updated gate','perimeter_only':True,'identification_mode':'BOTH'})
    assert update.status_code==200,update.text
    assert update.json()['terminal_role']=='PERIMETER_BOTH'
    # No backdoor conversion into a cell without its required configuration.
    response=client.put(f"/api/v1/admin/perimeter/terminals/{gate['code']}/role",json={'factory_code':'DEFAULT','role':'CELL'})
    assert response.status_code in (409,422)


def test_cell_requirements_remain_and_conversion_clears_time_configuration(monitor):
    client, db = monitor
    cell,_=configured_terminal(client)
    assert client.post('/api/v1/admin/terminals',json={'name':'Missing cell config'}).status_code==422
    response=client.put('/api/v1/admin/terminals/CLOCK-A',json={'name':'Perimeter conversion','perimeter_only':True})
    assert response.status_code==200,response.text
    gate=response.json()
    assert gate['project_line_id'] is None and gate['action_codes']==[]
    assert gate['oracle_attributes']=={} and gate['exit_policy_mode']=='DISABLED'
    assert gate['external_device_id']==cell['external_device_id']
