"""Perimeter concurrency and reversible migrations on isolated PostgreSQL."""
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from test_exit_policy_postgres import pg_schema, migrate
from app.domain.enums import IdentificationMethod
from app.models.action import Action
from app.models.terminal import Terminal
from app.models.time_event import TimeEvent
from app.models.perimeter import FactoryPerimeterEvent, FactoryPerimeterSettings
from app.models.transmission_attempt import TransmissionAttempt
from app.services.event_service import scan
from app.services.perimeter_service import is_inside

pytestmark = pytest.mark.skipif(not os.environ.get('POLICY_TEST_DATABASE_URL'), reason='Requires isolated PostgreSQL')


def test_perimeter_upgrade_downgrade_preserves_legacy_data(pg_schema):
    engine, url = pg_schema
    migrate(url, '0009_operational_structure')
    with engine.begin() as c:
        c.execute(text("INSERT INTO terminals (code,name,external_device_id,identification_mode,reporter_id_type,oracle_attributes,active,created_at,updated_at) VALUES ('LEGACY','Legacy','LEGACY','BOTH','BADGE','{}',true,now(),now())"))
        before = c.execute(text('SELECT row_to_json(t)::text FROM terminals t')).scalar_one()
    migrate(url)
    with engine.connect() as c:
        assert c.execute(text('SELECT terminal_role,factory_code FROM terminals')).one() == ('CELL','DEFAULT')
        assert c.execute(text('SELECT count(*) FROM factory_perimeter_settings WHERE enabled')).scalar_one() == 0
    result = subprocess.run(['alembic','downgrade','0009_operational_structure'], env={**os.environ,'DATABASE_URL':url.render_as_string(hide_password=False)},capture_output=True,text=True)
    assert result.returncode == 0, result.stderr
    with engine.connect() as c:
        assert c.execute(text('SELECT row_to_json(t)::text FROM terminals t')).scalar_one() == before
    migrate(url)


def test_concurrent_gate_and_cell_scans_are_atomic(pg_schema):
    engine, url = pg_schema
    migrate(url)
    with Session(engine) as db:
        enter = Action(code='START',label='Start',supplier_device_event='START',state_effect='ENTER')
        leave = Action(code='AUTO_EXIT_FACTORY_PERIMETER',label='Automatic perimeter exit',supplier_device_event='AUTO_EXIT',state_effect='EXIT')
        db.add_all([
            Terminal(code='CELL',name='Cell',external_device_id='CELL',actions=[enter,leave]),
            Terminal(code='GATE',name='Gate',external_device_id='GATE',terminal_role='PERIMETER_BOTH'),
            Terminal(code='EXIT',name='Exit',external_device_id='EXIT',terminal_role='PERIMETER_EXIT'),
            FactoryPerimeterSettings(factory_code='DEFAULT',enabled=True,dedup_enabled=True,dedup_seconds=5,auto_exit_action_code=leave.code),
        ])
        db.commit()
    def round(terminals):
        barrier = Barrier(len(terminals))
        def capture(code):
            with Session(engine) as db:
                barrier.wait()
                try:
                    return scan(db,code,'00000001',IdentificationMethod.RFID).flow
                except HTTPException as e:
                    return e.status_code
        with ThreadPoolExecutor(max_workers=len(terminals)) as pool:
            return list(pool.map(capture,terminals))
    results = round(['GATE'] * 8)
    assert results.count('FACTORY_ENTRY_RECORDED') == 1
    assert results.count('DUPLICATE_IGNORED') == 7
    results = round(['CELL'] * 8)
    assert results.count('ENTRY_RECORDED') == 1
    assert results.count('DUPLICATE_IGNORED') == 7
    # Race cell scans against dedicated gate exit, including repeated gate exits.
    results = round(['EXIT'] * 4 + ['CELL'] * 4)
    assert results.count('FACTORY_EXIT_RECORDED') == 1
    with Session(engine) as db:
        assert not is_inside(db,'DEFAULT','00000001')
        events = db.scalars(select(TimeEvent).order_by(TimeEvent.event_datetime)).all()
        assert [e.state_effect for e in events] == ['ENTER','EXIT']
        assert all(e.delivery_status == 'PENDING' for e in events)
        movements = db.scalars(select(FactoryPerimeterEvent).order_by(FactoryPerimeterEvent.event_datetime)).all()
        assert [e.direction for e in movements] == ['ENTER','EXIT']
        assert movements[-1].auto_cell_exit_event_id == events[-1].id
        assert movements[-1].correlation_id == events[-1].correlation_id
        assert movements[-1].event_datetime == events[-1].event_datetime
        assert db.scalar(select(func.count()).select_from(TransmissionAttempt)) == 0
