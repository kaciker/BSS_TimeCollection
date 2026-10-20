"""HTTP E2E validation; MUST run only against the isolated replica API."""
import httpx
from sqlalchemy import text
from app.db.session import engine
from app.core.config import settings

assert 'bss-perimeter-validation-db' in settings.database_url
assert not settings.oracle_enabled
client = httpx.Client(base_url='http://bss-perimeter-validation-web',timeout=20)
def call(method, path, payload=None, expected=200):
    result = client.request(method, '/api/v1/'+path, json=payload)
    assert result.status_code == expected, (path,result.status_code,result.text)
    return result.json()
assert call('GET','health/ready')['status'] == 'ready'
assert client.get('/').status_code == 200
assert call('GET','admin/perimeter/DEFAULT')['enabled'] is False
# Only the isolated replica is configured with simulated cards and readers.
entry = call('POST','admin/actions',dict(code='E2E_ENTER',label='Test entry',supplier_device_event='E2E_ENTER',state_effect='ENTER',display_order=100,oracle_attributes={}),201)
leave = call('POST','admin/actions',dict(code='E2E_AUTO_EXIT',label='Test automatic exit',supplier_device_event='E2E_EXIT',state_effect='EXIT',display_order=101,oracle_attributes={}),201)
w = call('POST','admin/structure/workshops',dict(code='E2E_W',description='Test'),201)
s = call('POST','admin/structure/subworkshops',dict(code='E2E_S',description='Test',workshop_id=w['id']),201)
p = call('POST','admin/structure/project-lines',dict(code='E2E_P',description='Test',subworkshop_id=s['id']),201)
terminals = {}
for code, role, mode in [('E2E_CELL','CELL','BOTH'),('E2E_GATE','PERIMETER_ENTER','RFID'),('E2E_EXIT','PERIMETER_EXIT','BOTH')]:
    terminals[code] = call('POST','admin/terminals',dict(code=code,name=code,external_device_id=code,identification_mode=mode,reporter_id_type='BADGE',oracle_attributes={},active=True,project_line_id=p['id'],workshop_id=w['id'],subworkshop_id=s['id'],action_codes=['E2E_ENTER','E2E_AUTO_EXIT']),201)
    call('PUT',f'admin/perimeter/terminals/{code}/role',dict(factory_code='E2E',role=role))
call('PUT','admin/perimeter/E2E',dict(enabled=True,badge_source='OPEN',dedup_enabled=True,dedup_seconds=5,auto_exit_action_code='E2E_AUTO_EXIT'))
def activate(code):
    token=call('POST',f'admin/terminals/{code}/provision')['activation_token']
    call('POST','terminal/activate',dict(token=token))
def scan(expected=200,method='RFID'):
    return call('POST','terminal/scan',dict(reporter_id='0000-E2E-ONLY',identification_method=method),expected)
activate('E2E_CELL'); scan(409)
activate('E2E_GATE'); scan(409,'KEYPAD')
assert scan()['flow'] == 'FACTORY_ENTRY_RECORDED'
assert scan()['flow'] == 'DUPLICATE_IGNORED'
activate('E2E_CELL'); assert scan()['flow'] == 'ENTRY_RECORDED'
activate('E2E_EXIT'); assert scan()['flow'] == 'FACTORY_EXIT_RECORDED'
assert scan()['flow'] == 'DUPLICATE_IGNORED'
activate('E2E_CELL'); scan(409)
with engine.connect() as c:
    events=c.execute(text("SELECT state_effect,correlation_id,event_datetime FROM time_events WHERE reporter_id='0000-E2E-ONLY' ORDER BY event_datetime")).all()
    assert [e.state_effect for e in events] == ['ENTER','EXIT']
    gate=c.execute(text("SELECT correlation_id,event_datetime,auto_cell_exit_event_id FROM factory_perimeter_events WHERE reporter_id='0000-E2E-ONLY' AND direction='EXIT'")).one()
    assert gate.correlation_id==events[-1].correlation_id and gate.event_datetime==events[-1].event_datetime
    assert c.execute(text('SELECT count(*) FROM transmission_attempts')).scalar_one()==0
call('PUT','admin/perimeter/E2E',dict(enabled=False,badge_source='OPEN',dedup_enabled=False,dedup_seconds=5,auto_exit_action_code='E2E_AUTO_EXIT'))
assert scan(method='KEYPAD')['flow']=='ENTRY_RECORDED'
assert scan(method='KEYPAD')['flow']=='EXIT_REQUIRED'
assert call('POST','terminal/exit',dict(reporter_id='0000-E2E-ONLY',identification_method='KEYPAD',action_code='E2E_AUTO_EXIT'))['flow']=='EXIT_RECORDED'
print('PASS: HTTP web/API health, provisioning, RFID/BOTH/KEYPAD, entry guard, duplicates, atomic cascade, queue isolation, disabled legacy capture; simulated UID only in replica')
