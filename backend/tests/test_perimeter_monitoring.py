from test_monitoring import monitor
from test_configuration import configured_terminal
from app.models.terminal import Terminal
from app.models.time_event import TimeEvent
from app.models.perimeter import FactoryPerimeterEvent
from app.services.event_service import scan
from app.domain.enums import IdentificationMethod
from sqlalchemy import select
from fastapi import HTTPException
import pytest


def test_combined_log_lists_and_inspects_local_perimeter_events(monitor):
    client,db=monitor
    configured_terminal(client)
    gate=Terminal(code='GATE',name='Gate',external_device_id='GATE',terminal_role='PERIMETER_BOTH')
    db.add(gate);db.commit()
    client.put('/api/v1/admin/perimeter/DEFAULT',json={'enabled':True,'auto_exit_action_code':'STOP','dedup_enabled':False})
    scan(db,'GATE','0001',IdentificationMethod.RFID)
    scan(db,'CLOCK-A','0001',IdentificationMethod.RFID)
    scan(db,'GATE','0001',IdentificationMethod.RFID)
    response=client.get('/api/v1/admin/monitoring/events')
    assert response.status_code==200,response.text
    data=response.json();assert data['total']==4
    local=[e for e in data['items'] if e['event_kind']=='PERIMETER']
    assert len(local)==2 and all(e['delivery_status']=='LOCAL_ONLY' for e in local)
    assert client.get('/api/v1/admin/monitoring/events?terminal_code=GATE').json()['total']==2
    assert client.get('/api/v1/admin/monitoring/events?delivery_status=LOCAL_ONLY').json()['total']==2
    assert client.get('/api/v1/admin/monitoring/events?delivery_status=PENDING').json()['total']==2
    assert client.get('/api/v1/admin/monitoring/events?reporter_id=%25').json()['total']==0
    assert client.get('/api/v1/admin/monitoring/events?limit=1&offset=3').json()['total']==4
    assert 'GATE' in client.get('/api/v1/admin/monitoring/clocks').json()
    detail=client.get('/api/v1/admin/monitoring/events/'+local[0]['id'])
    assert detail.status_code==200,detail.text
    assert detail.json()['oracle_payload_preview'] is None
    assert detail.json()['attempts']==[]
    assert len(db.scalars(select(TimeEvent)).all())==2


def test_presence_must_be_in_the_same_factory_and_entry_rejected_without_events(monitor):
    client,db=monitor
    configured_terminal(client)
    cell=db.scalar(select(Terminal).where(Terminal.code=='CLOCK-A'))
    cell.factory_code='ARGANDA'
    db.add(Terminal(code='GATE',name='Gate',external_device_id='GATE',terminal_role='PERIMETER_ENTER',factory_code='OTHER'))
    db.commit()
    for factory in ['ARGANDA','OTHER']:
        assert client.put('/api/v1/admin/perimeter/'+factory,json={'enabled':True,'auto_exit_action_code':'STOP'}).status_code==200
    scan(db,'GATE','0001',IdentificationMethod.RFID)
    with pytest.raises(HTTPException) as error:
        scan(db,'CLOCK-A','0001',IdentificationMethod.RFID)
    assert error.value.status_code==409
    db.rollback()
    assert db.scalars(select(TimeEvent)).all()==[]


def test_cards_include_perimeter_only_badges_with_local_details(monitor):
    from datetime import datetime, timezone
    client, db = monitor
    gate = Terminal(code='GATE', name='Main Entry', external_device_id='GATE', terminal_role='PERIMETER_BOTH')
    db.add(gate); db.flush()
    for badge, direction in [('0001', 'ENTER'), ('0002', 'EXIT')]:
        db.add(FactoryPerimeterEvent(id='gate-'+badge, factory_code='DEFAULT', reporter_id=badge,
            terminal_id=gate.id, direction=direction, event_datetime=datetime(2026,10,9,12,0,tzinfo=timezone.utc), correlation_id=badge))
    db.commit()
    response = client.get('/api/v1/admin/monitoring/cards?terminal_code=GATE&reporter_id=0001')
    assert response.status_code == 200, response.text
    card = response.json()['items'][0]
    assert response.json()['total'] == 1
    assert card['reporter_id'] == '0001' and card['worker_state'] == 'OUTSIDE'
    assert card['event']['event_kind'] == 'PERIMETER' and card['event']['delivery_status'] == 'LOCAL_ONLY'
    assert card['event']['terminal_code'] == 'GATE'
    detail = client.get('/api/v1/admin/monitoring/events/'+card['event']['id']).json()
    assert detail['attempts'] == [] and detail['oracle_payload_preview'] is None
    outside = client.get('/api/v1/admin/monitoring/cards?terminal_code=GATE&reporter_id=0002').json()
    assert outside['items'][0]['reporter_id'] == '0002'
    assert client.get('/api/v1/admin/monitoring/cards?reporter_id=%25').json()['total'] == 0
    page = client.get('/api/v1/admin/monitoring/cards?limit=1&offset=1').json()
    assert page['total'] == 2 and page['items'][0]['reporter_id'] == '0002'
    assert db.scalars(select(TimeEvent)).all() == []


def test_cards_rank_across_gate_and_cell_before_clock_filter(monitor):
    from datetime import datetime, timezone
    from test_monitoring import add_event
    client, db = monitor
    gate = Terminal(code='GATE', name='Gate', external_device_id='GATE', terminal_role='PERIMETER_BOTH')
    db.add(gate); db.flush()
    for badge, minute, direction in [('0001', 0, 'ENTER'), ('0002', 2, 'EXIT')]:
        db.add(FactoryPerimeterEvent(id='gate-'+badge, factory_code='DEFAULT', reporter_id=badge,
            terminal_id=gate.id, direction=direction, event_datetime=datetime(2026,10,9,12,minute,tzinfo=timezone.utc), correlation_id=badge))
    db.commit()
    add_event(db, '0001', 'CELL', 'ENTER', 1)
    add_event(db, '0002', 'CELL', 'ENTER', 0)
    gate_cards = client.get('/api/v1/admin/monitoring/cards?terminal_code=GATE').json()
    assert gate_cards['total'] == 1 and gate_cards['items'][0]['reporter_id'] == '0002'
    assert gate_cards['items'][0]['worker_state'] == 'INSIDE'
    cell_cards = client.get('/api/v1/admin/monitoring/cards?terminal_code=CELL&worker_state=INSIDE').json()
    assert cell_cards['total'] == 1 and cell_cards['items'][0]['reporter_id'] == '0001'


def test_cards_cascade_shared_timestamp_finishes_at_perimeter(monitor):
    from datetime import datetime, timedelta, timezone
    from test_monitoring import add_event
    client, db = monitor
    gate = Terminal(code='GATE', name='Gate', external_device_id='GATE', terminal_role='PERIMETER_BOTH')
    db.add(gate); db.flush()
    at = datetime(2026,10,9,12,2,tzinfo=timezone.utc)
    db.add(FactoryPerimeterEvent(id='gate-last', factory_code='DEFAULT', reporter_id='0001',
        terminal_id=gate.id, direction='EXIT', event_datetime=at, correlation_id='cascade'))
    db.commit()
    add_event(db, '0001', 'CELL', 'ENTER', 0)
    exit_event = add_event(db, '0001', 'CELL', 'EXIT', 2)
    exit_event.created_at = at + timedelta(milliseconds=10)
    db.commit()
    result = client.get('/api/v1/admin/monitoring/cards?reporter_id=0001').json()
    assert result['total'] == 1
    assert result['items'][0]['worker_state'] == 'OUTSIDE'
    assert result['items'][0]['event']['id'] == 'perimeter:gate-last'
    assert client.get('/api/v1/admin/monitoring/cards?terminal_code=CELL').json()['total'] == 0


def test_cell_and_factory_state_are_independent_and_filters_compose(monitor):
    from datetime import datetime, timezone
    from test_monitoring import add_event
    from app.models.perimeter import FactoryPerimeterSettings
    client, db = monitor
    gate=Terminal(code='GATE',name='Gate',external_device_id='GATE',terminal_role='PERIMETER_BOTH',factory_code='ARGANDA')
    db.add(gate); db.flush()
    db.add(FactoryPerimeterSettings(factory_code='ARGANDA',enabled=True))
    for badge in ['001','002']:
        db.add(FactoryPerimeterEvent(id='entry-'+badge,factory_code='ARGANDA',reporter_id=badge,terminal_id=gate.id,direction='ENTER',event_datetime=datetime(2026,10,9,12,0,tzinfo=timezone.utc),correlation_id=badge))
    db.commit()
    add_event(db,'001','CELL','ENTER',1)
    add_event(db,'001','CELL','EXIT',2)
    page=client.get('/api/v1/admin/monitoring/cards?worker_state=OUTSIDE&factory_state=INSIDE').json()
    assert page['factory_perimeter_enabled'] is True and page['total']==2
    assert all(c['worker_state']=='OUTSIDE' and c['factory_state']=='INSIDE' and c['factory_code']=='ARGANDA' for c in page['items'])
    assert client.get('/api/v1/admin/monitoring/cards?worker_state=INSIDE&factory_state=INSIDE').json()['total']==0
    db.add(FactoryPerimeterEvent(id='exit-001',factory_code='ARGANDA',reporter_id='001',terminal_id=gate.id,direction='EXIT',event_datetime=datetime(2026,10,9,12,3,tzinfo=timezone.utc),correlation_id='exit'))
    db.commit()
    outside=client.get('/api/v1/admin/monitoring/cards?factory_state=OUTSIDE').json()
    assert outside['total']==1 and outside['items'][0]['reporter_id']=='001'
    assert client.get('/api/v1/admin/monitoring/cards?factory_state=INSIDE&limit=1').json()['total']==1
    config=db.get(FactoryPerimeterSettings,'ARGANDA'); config.enabled=False; db.commit()
    disabled=client.get('/api/v1/admin/monitoring/cards').json()
    assert disabled['factory_perimeter_enabled'] is False
    assert all(c['factory_state'] is None for c in disabled['items'])
    assert client.get('/api/v1/admin/monitoring/cards?factory_state=INSIDE').json()['total']==0


def test_factory_state_does_not_leak_from_another_factory(monitor):
    from datetime import datetime, timezone
    from app.models.perimeter import FactoryPerimeterSettings
    client,db=monitor
    for factory,minute in [('ARGANDA',0),('OTHER',1)]:
        gate=Terminal(code=factory,name=factory,external_device_id=factory,terminal_role='PERIMETER_BOTH',factory_code=factory)
        db.add(gate);db.flush()
        db.add(FactoryPerimeterSettings(factory_code=factory,enabled=factory=='ARGANDA'))
        db.add(FactoryPerimeterEvent(id=factory,factory_code=factory,reporter_id='001',terminal_id=gate.id,direction='ENTER',event_datetime=datetime(2026,10,9,12,minute,tzinfo=timezone.utc),correlation_id=factory))
    db.commit()
    page=client.get('/api/v1/admin/monitoring/cards').json()
    assert page['factory_perimeter_enabled'] is True
    assert page['items'][0]['factory_code']=='OTHER' and page['items'][0]['factory_state'] is None
    assert client.get('/api/v1/admin/monitoring/cards?factory_state=INSIDE').json()['total']==0
