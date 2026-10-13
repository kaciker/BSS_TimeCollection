"""HTTP capture smoke test. Run inside the target API container after backup.
Creates uniquely named test actions/terminals/events; retires only those terminals.
The global policy is read and MUST remain Disabled throughout.
"""
from uuid import uuid4
import httpx
from sqlalchemy import func, select
from app.db.session import SessionLocal
from app.models.time_event import TimeEvent
from app.models.transmission_attempt import TransmissionAttempt

base='http://127.0.0.1:8000'
path='/api/v1/admin/policies/same-terminal-exit'
prefix='POLICY-CHECK-'+uuid4().hex[:8]
admin=httpx.Client(base_url=base,timeout=20)
browsers=[]
created=[]
checks=[]


def request(client,method,url,payload=None,status=200):
    r=client.request(method,url,json=payload)
    assert r.status_code==status,(url,r.status_code,r.text)
    return r.json()


def counts(badge):
    with SessionLocal() as db:
        events=db.scalar(select(func.count()).select_from(TimeEvent).where(TimeEvent.reporter_id==badge))
        attempts=db.scalar(select(func.count()).select_from(TransmissionAttempt).join(TimeEvent,TimeEvent.id==TransmissionAttempt.event_id).where(TimeEvent.reporter_id==badge))
        return events,attempts


def policy(code,mode):
    return request(admin,'PUT',path+'/terminals/'+code,{'mode':mode})


def cell(code,value):
    return request(admin,'PUT',path+'/terminals/'+code+'/work-cell',{'work_cell':value})


def scan(browser,badge,status=200):
    return request(browser,'POST','/api/v1/terminal/scan',{'reporter_id':badge,'identification_method':'KEYPAD'},status)


def leave(browser,badge,status=200):
    return request(browser,'POST','/api/v1/terminal/exit',{'reporter_id':badge,'identification_method':'KEYPAD','action_code':prefix+'-EXIT'},status)


try:
    assert request(admin,'GET',path)['global_mode']=='DISABLED'
    for effect in ['ENTER','EXIT']:
        request(admin,'POST','/api/v1/admin/actions',{'code':prefix+'-'+effect,'label':'Policy validation '+effect.lower(),'supplier_device_event':prefix+'-'+effect,'state_effect':effect},201)
    for suffix in ['A','B']:
        code=prefix+'-'+suffix
        terminal=request(admin,'POST','/api/v1/admin/terminals',{'code':code,'name':'Policy validation '+suffix,'external_device_id':code,'identification_mode':'KEYPAD','oracle_attributes':{'Workshop':'Policy validation','work_cell':'CELL-A'},'action_codes':[prefix+'-ENTER',prefix+'-EXIT']},201)
        created.append(code)
        browser=httpx.Client(base_url=base,timeout=20)
        browsers.append(browser)
        request(browser,'POST','/api/v1/terminal/activate',{'token':terminal['activation_token']})
    a,b=created
    for n,(mode,ca,cb,target,allowed) in enumerate([
        ('DISABLED','CELL-A','CELL-B',1,True),
        ('SAME_TERMINAL','CELL-A','CELL-A',0,True),
        ('SAME_TERMINAL','CELL-A','CELL-A',1,False),
        ('SAME_WORK_CELL','CELL-A','CELL-A',1,True),
        ('SAME_WORK_CELL','CELL-A','CELL-B',1,False),
        ('SAME_WORK_CELL','','CELL-A',1,False),
        ('SAME_WORK_CELL','CELL-A','',1,False),
        ('INHERIT','CELL-A','CELL-B',1,True),
    ]):
        badge=prefix+'-'+str(n)
        cell(a,ca);cell(b,cb);policy(a,mode);policy(b,mode)
        assert scan(browsers[0],badge)['flow']=='ENTRY_RECORDED'
        before=counts(badge)
        s=scan(browsers[target],badge,200 if allowed else 409)
        r=leave(browsers[target],badge,200 if allowed else 409)
        if allowed:
            assert s['flow']=='EXIT_REQUIRED' and r['flow']=='EXIT_RECORDED'
            assert counts(badge)==(2,0)
        else:
            assert counts(badge)==before==(1,0),'Rejected exit created a local/Oracle queue event'
            assert 'No exit was recorded' in r['detail']
            policy(a,'DISABLED');leave(browsers[0],badge)
        checks.append({'mode':mode,'entry_cell':ca,'exit_cell':cb,'same_terminal':target==0,'allowed':allowed,'rejected_oracle_events':0})
    for code in created:policy(code,'INHERIT')
    assert request(admin,'GET',path)['global_mode']=='DISABLED'
    print({'terminals':created,'checks':checks,'global':'DISABLED','rejected_oracle_events':0})
finally:
    for code in created:
        request(admin,'DELETE','/api/v1/admin/terminals/'+code)
    for browser in browsers:browser.close()
    admin.close()
