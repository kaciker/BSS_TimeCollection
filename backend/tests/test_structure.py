import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.structure import Workshop, Subworkshop, ProjectLine
from app.models.terminal import Terminal
from app.models.time_event import TimeEvent
from app.models.action import Action
from app.domain.enums import IdentificationMethod
from app.services.event_service import _create_event
from app.integrations.oracle.client import OracleClient

@pytest.fixture
def structure_client():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        app.dependency_overrides[get_db]=lambda:db
        with TestClient(app) as client: yield client,db
        app.dependency_overrides.clear()
    engine.dispose()

def post(client, path, **data):
    response=client.post("/api/v1/admin/structure/"+path,json=data)
    assert response.status_code==201,response.text
    return response.json()

def test_hierarchy_scoping_parent_validation_and_lifecycle(structure_client):
    client,db=structure_client
    w1=post(client,"workshops",code="428",description="Extrusion",active=True)
    w2=post(client,"workshops",code="429",description="Other",active=True)
    assert client.post("/api/v1/admin/structure/workshops",json={"code":"428","description":"Duplicate"}).status_code==409
    s1=post(client,"subworkshops",workshop_id=w1["id"],code="A",description="First")
    s2=post(client,"subworkshops",workshop_id=w2["id"],code="A",description="Second")
    assert client.post("/api/v1/admin/structure/subworkshops",json={"workshop_id":999,"code":"A","description":"Bad"}).status_code==404
    p1=post(client,"project-lines",subworkshop_id=s1["id"],code="1",description="Line one")
    p2=post(client,"project-lines",subworkshop_id=s2["id"],code="1",description="Other one")
    assert p1["id"]!=p2["id"]
    assert client.post("/api/v1/admin/structure/project-lines",json={"subworkshop_id":s1["id"],"code":"1","description":"Duplicate"}).status_code==409
    assert client.put(f"/api/v1/admin/structure/project-lines/{p1['id']}",json={"subworkshop_id":s1["id"],"code":"1","description":"Renamed","active":False}).json()["active"] is False
    assert client.put(f"/api/v1/admin/structure/project-lines/{p1['id']}",json={"subworkshop_id":s1["id"],"code":"1","description":"Renamed","active":True}).json()["description"]=="Renamed"
    assert len(client.get("/api/v1/admin/structure").json()["project_lines"])==2
    assert client.put(f"/api/v1/admin/structure/subworkshops/{s1[chr(105)+chr(100)]}",json={"workshop_id":w2["id"],"code":"A","description":"Moved","active":True}).status_code==409
    assert client.put(f"/api/v1/admin/structure/workshops/{w1[chr(105)+chr(100)]}",json={"code":"428","description":"Extrusion","active":False}).status_code==409

def test_terminal_path_snapshot_and_oracle_attributes(structure_client):
    client,db=structure_client
    w=post(client,"workshops",code="W",description="Workshop")
    s=post(client,"subworkshops",workshop_id=w["id"],code="S",description="Sub")
    leaf=post(client,"project-lines",subworkshop_id=s["id"],code="P",description="Project")
    other=post(client,"workshops",code="X",description="Wrong")
    for code,effect in [("IN","ENTER"),("OUT","EXIT")]:
        response=client.post("/api/v1/admin/actions",json={"code":code,"label":code,"supplier_device_event":code,"state_effect":effect})
        assert response.status_code==201,response.text
    body={"code":"TEST","name":"Test","external_device_id":"DEV-TEST","identification_mode":"BOTH","active":True,"action_codes":["IN","OUT"],"oracle_attributes":{"Plant":"legacy","unknown":"preserved","work_cell":"A"},"workshop_id":w["id"],"subworkshop_id":s["id"],"project_line_id":leaf["id"]}
    assert client.post("/api/v1/admin/terminals",json={**body,"project_line_id":None}).status_code==422
    assert client.post("/api/v1/admin/terminals",json={**body,"workshop_id":other["id"]}).status_code==422
    created=client.post("/api/v1/admin/terminals",json=body)
    assert created.status_code==201,created.text
    assert created.json()["structure_path"]=="W / S / P"
    assert created.json()["oracle_attributes"]==body["oracle_attributes"]
    terminal=db.scalar(select(Terminal).where(Terminal.code=="TEST"))
    action=db.scalar(select(Action).where(Action.code=="IN"))
    event=_create_event(db,terminal,action,"TEST-BADGE",IdentificationMethod.KEYPAD)
    assert (event.workshop_code,event.subworkshop_code,event.project_line_code)==("W","S","P")
    assert (event.workshop_description,event.subworkshop_description,event.project_line_description)==("Workshop","Sub","Project")
    assert event.oracle_attributes=={"Plant":"legacy","unknown":"preserved"}
    assert {x["name"] for x in OracleClient().build_payload(event)["timeEvents"][0]["timeEventAttributes"]} == {"Plant", "unknown"}
    db.get(ProjectLine,leaf["id"]).description="Changed";db.commit();db.refresh(event)
    assert event.project_line_description=="Project"
    assert client.post("/api/v1/admin/terminals/TEST/clone",json={}).json()["project_line_id"]==leaf["id"]

def test_legacy_terminal_and_event_remain_readable(structure_client):
    client,db=structure_client
    t=Terminal(code="LEGACY",name="Legacy",external_device_id="LEGACY",oracle_attributes={"work_cell":"C","custom":"keep"},active=False)
    db.add(t);db.commit()
    row=next(x for x in client.get("/api/v1/admin/terminals").json() if x["code"]=="LEGACY")
    assert row["project_line_id"] is None
    assert row["oracle_attributes"]["custom"]=="keep"
