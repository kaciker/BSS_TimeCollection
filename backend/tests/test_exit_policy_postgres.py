"""Real PostgreSQL regression checks; run only against the isolated validation DB."""
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domain.enums import IdentificationMethod
from app.models.action import Action
from app.models.exit_policy import policies
from app.models.terminal import Terminal
from app.models.time_event import TimeEvent
from app.models.transmission_attempt import TransmissionAttempt
from app.services.event_service import record_exit, scan
from app.services.exit_policy import get_mode, save_mode

pytestmark=pytest.mark.skipif(not os.environ.get('POLICY_TEST_DATABASE_URL'),reason='Requires isolated PostgreSQL validation DB')


@pytest.fixture
def pg_schema():
    url=make_url(os.environ['POLICY_TEST_DATABASE_URL'])
    assert url.database=='bss_policy_test','Only the isolated validation database is allowed'
    schema='policy_test_'+uuid4().hex
    admin=create_engine(url)
    with admin.begin() as c:c.execute(text(f'CREATE SCHEMA "{schema}"'))
    test_url=url.update_query_dict({'options':f'-csearch_path={schema}'})
    engine=create_engine(test_url,pool_size=20,max_overflow=0)
    try:yield engine,test_url
    finally:
        engine.dispose()
        with admin.begin() as c:c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def migrate(url,revision='head',expect=True):
    result=subprocess.run(['alembic','upgrade',revision],env={**os.environ,'DATABASE_URL':url.render_as_string(hide_password=False)},capture_output=True,text=True)
    assert (result.returncode==0)==expect,result.stderr
    return result


def test_postgres_fresh_migration_and_legacy_adoption(pg_schema):
    engine,url=pg_schema
    migrate(url,'0007_seed_action_visuals')
    with engine.begin() as c:
        c.execute(text('CREATE TABLE exit_policies (id SERIAL PRIMARY KEY, terminal_id INTEGER UNIQUE, mode VARCHAR(32) NOT NULL)'))
        c.execute(text("INSERT INTO exit_policies (terminal_id,mode) VALUES (NULL,'DISABLED')"))
    migrate(url)
    migrate(url)
    with engine.connect() as c:
        assert c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()=='0011_action_visibility'
        assert c.execute(text('SELECT mode FROM exit_policies')).scalar_one()=='DISABLED'
    with pytest.raises(Exception):
        with engine.begin() as c:c.execute(text("INSERT INTO exit_policies (terminal_id,mode) VALUES (NULL,'SAME_TERMINAL')"))


def test_postgres_duplicate_legacy_globals_fail_without_data_loss(pg_schema):
    engine,url=pg_schema
    migrate(url,'0007_seed_action_visuals')
    with engine.begin() as c:
        c.execute(text('CREATE TABLE exit_policies (id SERIAL PRIMARY KEY, terminal_id INTEGER UNIQUE, mode VARCHAR(32) NOT NULL)'))
        c.execute(text("INSERT INTO exit_policies (terminal_id,mode) VALUES (NULL,'DISABLED'),(NULL,'SAME_TERMINAL')"))
    result=migrate(url,expect=False)
    assert 'duplicate scopes' in result.stderr
    with engine.connect() as c:
        assert c.execute(text('SELECT count(*) FROM exit_policies')).scalar_one()==2
        assert c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()=='0007_seed_action_visuals'


def test_postgres_concurrent_policy_upserts_and_persistence(pg_schema):
    engine,url=pg_schema
    migrate(url)
    def round(scope):
        barrier=Barrier(12)
        def save(index):
            with Session(engine) as db:
                barrier.wait()
                save_mode(db,scope,['DISABLED','SAME_TERMINAL','SAME_WORK_CELL'][index%3])
        with ThreadPoolExecutor(max_workers=12) as pool:list(pool.map(save,range(12)))
    round(None)
    with Session(engine) as db:
        terminal=Terminal(code='OVERRIDE',name='Override',external_device_id='OVERRIDE',active=False)
        db.add(terminal);db.commit();terminal_id=terminal.id
    round(terminal_id)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(policies).where(policies.c.terminal_id==terminal_id))==1
        save_mode(db,terminal_id,'INHERIT')
        assert get_mode(db,terminal_id)==get_mode(db,None)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(policies))==1
        assert get_mode(db,None) in {'DISABLED','SAME_TERMINAL','SAME_WORK_CELL'}
        save_mode(db,None,'DISABLED')
    with Session(engine) as db:assert get_mode(db,None)=='DISABLED'


def test_postgres_concurrent_capture_serializes_badge_and_rejects_without_oracle(pg_schema):
    engine,url=pg_schema
    migrate(url)
    with Session(engine) as db:
        enter=Action(code='ENTER',label='Entry',supplier_device_event='ENTER',state_effect='ENTER')
        leave=Action(code='EXIT',label='Exit',supplier_device_event='EXIT',state_effect='EXIT')
        a=Terminal(code='A',name='A',external_device_id='A',actions=[enter,leave])
        b=Terminal(code='B',name='B',external_device_id='B',actions=[enter,leave])
        db.add_all([a,b]);db.commit();aid=a.id;bid=b.id
        save_mode(db,aid,'SAME_TERMINAL');save_mode(db,bid,'SAME_TERMINAL')
    barrier=Barrier(8)
    def capture(index):
        with Session(engine) as db:
            barrier.wait()
            return scan(db,'A','concurrent',IdentificationMethod.KEYPAD).flow
    with ThreadPoolExecutor(max_workers=8) as pool:flows=list(pool.map(capture,range(8)))
    assert flows.count('ENTRY_RECORDED')==1 and flows.count('EXIT_REQUIRED')==7
    with Session(engine) as db:
        for _ in range(3):
            with pytest.raises(HTTPException) as err:record_exit(db,'B','concurrent',IdentificationMethod.KEYPAD,'EXIT')
            assert err.value.status_code==409
            db.rollback()
        assert db.scalar(select(func.count()).select_from(TimeEvent))==1
        assert db.scalar(select(func.count()).select_from(TransmissionAttempt))==0
    barrier=Barrier(8)
    def leave(index):
        with Session(engine) as db:
            barrier.wait()
            try:return record_exit(db,'A','concurrent',IdentificationMethod.KEYPAD,'EXIT').flow
            except HTTPException as e:return e.status_code
    with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(leave,range(8)))
    assert results.count('EXIT_RECORDED')==1 and results.count(409)==7
    with Session(engine) as db:assert db.scalar(select(func.count()).select_from(TimeEvent))==2
