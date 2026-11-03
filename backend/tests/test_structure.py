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
from app.models.factory import Factory, InstallationSettings
from app.domain.enums import IdentificationMethod
from app.services.event_service import _create_event
from app.integrations.oracle.client import OracleClient

@pytest.fixture
def structure_client():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([Factory(code="ARGANDA", name="Arganda"), InstallationSettings(id=1, default_factory_code="ARGANDA")])
        db.commit()
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
    w=post(client,"workshops",code="W",description="Workshop",oracle_work_area_code="439")
    s=post(client,"subworkshops",workshop_id=w["id"],code="S",description="Sub",oracle_machine_code="4391")
    leaf=post(client,"project-lines",subworkshop_id=s["id"],code="P",description="Project",oracle_cell_code="54Q")
    other=post(client,"workshops",code="X",description="Wrong")
    for code,effect in [("IN","ENTER"),("OUT","EXIT")]:
        response=client.post("/api/v1/admin/actions",json={"code":code,"label":code,"supplier_device_event":code,"state_effect":effect})
        assert response.status_code==201,response.text
    body={"code":"TEST","factory_code":"ARGANDA","name":"Test","external_device_id":"DEV-TEST","identification_mode":"BOTH","active":True,"action_codes":["IN","OUT"],"oracle_attributes":{"Plant":"legacy","unknown":"preserved","work_cell":"A"},"workshop_id":w["id"],"subworkshop_id":s["id"],"project_line_id":leaf["id"]}
    assert client.post("/api/v1/admin/terminals",json={**body,"project_line_id":None}).status_code==422
    assert client.post("/api/v1/admin/terminals",json={**body,"workshop_id":other["id"]}).status_code==422
    created=client.post("/api/v1/admin/terminals",json=body)
    assert created.status_code==201,created.text
    assert created.json()["structure_path"]=="W / S / P"
    assert (created.json()["oracle_work_area_code"], created.json()["oracle_machine_code"], created.json()["oracle_cell_code"]) == ("439", "4391", "54Q")
    assert created.json()["oracle_attributes"]==body["oracle_attributes"]
    terminal=db.scalar(select(Terminal).where(Terminal.code=="TEST"))
    action=db.scalar(select(Action).where(Action.code=="IN"))
    event=_create_event(db,terminal,action,"TEST-BADGE",IdentificationMethod.KEYPAD)
    event.person_id = "104582"
    event.oracle_payroll_time_type = "Workshop Entry ES"
    event.oracle_reporter_id = "104582"
    event.oracle_reporter_id_type = "PERSON"
    assert (event.workshop_code,event.subworkshop_code,event.project_line_code)==("W","S","P")
    assert (event.workshop_description,event.subworkshop_description,event.project_line_description)==("Workshop","Sub","Project")
    assert event.supplier_device_event == action.supplier_device_event
    assert event.oracle_supplier_event == "HUT_TCD_SUPP1_IN_2"
    assert event.oracle_attributes=={"Plant":"legacy","unknown":"preserved"}
    assert (event.oracle_work_area_code,event.oracle_machine_code,event.oracle_cell_code)==("439","4391","54Q")
    assert not hasattr(terminal,"oracle_work_area_code")
    payload = OracleClient().build_payload(event)["timeEvents"][0]
    assert [x["name"] for x in payload["timeEventAttributes"]] == ["PayrollTimeType", "WORK_AREA", "MACHINE", "CELL"]
    attributes = {x["name"]: x["value"] for x in payload["timeEventAttributes"]}
    assert (attributes["WORK_AREA"], attributes["MACHINE"], attributes["CELL"]) == ("439", "4391", "54Q")
    db.get(ProjectLine,leaf["id"]).description="Changed";db.commit();db.refresh(event)
    assert event.project_line_description=="Project"
    db.get(ProjectLine,leaf["id"]).oracle_cell_code=None;db.commit();db.refresh(event)
    assert event.oracle_cell_code=="54Q"
    assert OracleClient().build_payload(event)["timeEvents"][0]["timeEventAttributes"][-1]=={"name":"CELL","value":"54Q"}

def test_protected_contract_attributes_cannot_be_overridden_by_terminal_or_action(structure_client):
    client, db = structure_client
    w=post(client,"workshops",code="W-PROTECTED",description="Workshop",oracle_work_area_code="439")
    s=post(client,"subworkshops",workshop_id=w["id"],code="S-PROTECTED",description="Sub",oracle_machine_code="4391")
    p=post(client,"project-lines",subworkshop_id=s["id"],code="P-PROTECTED",description="Cell",oracle_cell_code="54Q")
    action_response=client.post("/api/v1/admin/actions",json={
        "code":"PROTECTED", "label":"Protected", "supplier_device_event":"BSS_PROTECTED",
        "state_effect":"ENTER", "oracle_payroll_time_type":"Workshop Entry ES",
        "oracle_attributes":{"PayrollTimeType":"Break ES","WORK_AREA":"bad","MACHINE":"bad","CELL":"bad"},
    })
    assert action_response.status_code==201, action_response.text
    terminal=Terminal(code="T-PROTECTED",name="Protected",external_device_id="T-PROTECTED",factory_code="ARGANDA",project_line_id=p["id"],active=True,
        oracle_attributes={"PayrollTimeType":"Break ES","WORK_AREA":"bad","MACHINE":"bad","CELL":"bad"})
    db.add(terminal);db.commit()
    event=_create_event(db,terminal,db.scalar(select(Action).where(Action.code=="PROTECTED")),"TEST",IdentificationMethod.KEYPAD)
    event.person_id="23703"
    item=OracleClient().build_payload(event)["timeEvents"][0]
    assert item["timeEventAttributes"]==[
        {"name":"PayrollTimeType","value":"Workshop Entry ES"},
        {"name":"WORK_AREA","value":"439"},
        {"name":"MACHINE","value":"4391"},
        {"name":"CELL","value":"54Q"},
    ]
    assert "deviceId" not in item

def test_enter_exit_supplier_events_are_frozen_from_action_direction(structure_client):
    client, db = structure_client
    w=post(client,"workshops",code="W-DIRECTION",description="Workshop",oracle_work_area_code="439")
    s=post(client,"subworkshops",workshop_id=w["id"],code="S-DIRECTION",description="Sub",oracle_machine_code="4391")
    p=post(client,"project-lines",subworkshop_id=s["id"],code="P-DIRECTION",description="Cell",oracle_cell_code="54Q")
    terminal=Terminal(code="T-DIRECTION",name="Direction",external_device_id="T-DIRECTION",factory_code="ARGANDA",project_line_id=p["id"],active=True)
    db.add(terminal);db.flush()
    enter=Action(code="DIR_ENTER",label="Enter",supplier_device_event="BSS_IN",oracle_supplier_event="HUT_TCD_SUPP1_IN_2",state_effect="ENTER",oracle_payroll_time_type="Workshop Entry ES")
    leave=Action(code="DIR_EXIT",label="Exit",supplier_device_event="BSS_OUT",oracle_supplier_event="HUT_TCD_SUPP1_OUT_2",state_effect="EXIT",oracle_payroll_time_type="Break ES")
    db.add_all([enter,leave]);db.commit()
    enter_event=_create_event(db,terminal,enter,"TEST",IdentificationMethod.KEYPAD)
    exit_event=_create_event(db,terminal,leave,"TEST",IdentificationMethod.KEYPAD)
    assert enter_event.oracle_supplier_event=="HUT_TCD_SUPP1_IN_2"
    assert enter_event.oracle_payroll_time_type=="Workshop Entry ES"
    assert exit_event.oracle_supplier_event=="HUT_TCD_SUPP1_OUT_2"
    assert exit_event.oracle_payroll_time_type=="Break ES"


def test_actions_may_share_directional_supplier_event_and_payroll_type(structure_client):
    client, _ = structure_client
    first = client.post("/api/v1/admin/actions", json={"code":"EXIT_A", "label":"Exit A", "supplier_device_event":"BSS_A", "oracle_supplier_event":"HUT_TCD_SUPP1_OUT_2", "state_effect":"EXIT", "oracle_payroll_time_type":"Break ES"})
    second = client.post("/api/v1/admin/actions", json={"code":"EXIT_B", "label":"Exit B", "supplier_device_event":"BSS_B", "oracle_supplier_event":"HUT_TCD_SUPP1_OUT_2", "state_effect":"EXIT"})
    invalid = client.post("/api/v1/admin/actions", json={"code":"BAD_IN", "label":"Bad direction", "supplier_device_event":"BSS_BAD", "oracle_supplier_event":"HUT_TCD_SUPP1_OUT_2", "state_effect":"ENTER"})
    assert first.status_code == second.status_code == 201
    assert first.json()["oracle_payroll_time_type"] == "Break ES"
    assert first.json()["supplier_device_event"] == "BSS_A"
    assert first.json()["oracle_supplier_event"] == "HUT_TCD_SUPP1_OUT_2"
    assert invalid.status_code == 422

def test_action_payroll_type_must_be_authoritative_and_directional_on_update(structure_client):
    client, _db = structure_client
    created=client.post("/api/v1/admin/actions",json={"code":"START_WORK","label":"Start work","supplier_device_event":"BSS_START","state_effect":"ENTER","oracle_payroll_time_type":"Workshop Entry ES"})
    assert created.status_code==201
    assert created.json()["oracle_ready"] is True
    invalid=client.put("/api/v1/admin/actions/START_WORK",json={**created.json(),"oracle_payroll_time_type":"Made Up"})
    assert invalid.status_code==422
    inconsistent=client.put("/api/v1/admin/actions/START_WORK",json={**created.json(),"state_effect":"EXIT","oracle_supplier_event":"HUT_TCD_SUPP1_IN_2","oracle_payroll_time_type":"Workshop Entry ES"})
    assert inconsistent.status_code==422

def test_mapping_catalogue_hierarchy_and_local_codes_are_independent(structure_client):
    client, _db = structure_client
    work_area = post(client, "workshops", code="local-439", description="Local label", oracle_work_area_code="439")
    machine = post(client, "subworkshops", workshop_id=work_area["id"], code="439.1", description="Local subworkshop", oracle_machine_code="4391")
    cell = post(client, "project-lines", subworkshop_id=machine["id"], code="LOCAL-P24", description="Local project line", oracle_cell_code="54Q")
    assert (work_area["code"], machine["code"], cell["code"]) == ("local-439", "439.1", "LOCAL-P24")
    catalogue = client.get("/api/v1/admin/structure/oracle-catalogue").json()
    assert {item["code"] for item in catalogue["work_areas"]} == {"439"}
    assert {item["code"] for item in catalogue["machines"]} == {"4391", "4392", "4393"}
    assert {item["code"] for item in catalogue["cells"]} == {"54Q", "54T"}
    p24 = post(client, "project-lines", subworkshop_id=machine["id"], code="LOCAL-P24-T", description="P24 G.V. Derecha", oracle_cell_code="54T")
    assert p24["oracle_cell_code"] == "54T"
    wrong_machine = client.post("/api/v1/admin/structure/subworkshops", json={"workshop_id": work_area["id"], "code":"wrong", "description":"wrong", "oracle_machine_code":"not-in-catalogue"})
    wrong_parent = post(client, "subworkshops", workshop_id=work_area["id"], code="other-machine", description="Other Oracle machine", oracle_machine_code="4392")
    wrong_cell = client.post("/api/v1/admin/structure/project-lines", json={"subworkshop_id": wrong_parent["id"], "code":"wrong", "description":"wrong", "oracle_cell_code":"54Q"})
    assert wrong_machine.status_code == 422
    assert wrong_cell.status_code == 422

def test_reparenting_oracle_mappings_must_match_new_hierarchy(structure_client):
    client, _db=structure_client
    first=post(client,"workshops",code="W-PARENT-1",description="First",oracle_work_area_code="439")
    second=post(client,"workshops",code="W-PARENT-2",description="Second")
    machine=post(client,"subworkshops",workshop_id=first["id"],code="S-PARENT",description="Machine",oracle_machine_code="4391")
    moved=client.put(f"/api/v1/admin/structure/subworkshops/{machine['id']}",json={"workshop_id":second["id"],"code":"S-PARENT","description":"Machine","active":True,"oracle_machine_code":"4391"})
    assert moved.status_code==422
    cell=post(client,"project-lines",subworkshop_id=machine["id"],code="P-PARENT",description="Cell",oracle_cell_code="54Q")
    other_machine=post(client,"subworkshops",workshop_id=first["id"],code="S-PARENT-2",description="Other machine",oracle_machine_code="4392")
    moved_cell=client.put(f"/api/v1/admin/structure/project-lines/{cell['id']}",json={"subworkshop_id":other_machine["id"],"code":"P-PARENT","description":"Cell","active":True,"oracle_cell_code":"54Q"})
    assert moved_cell.status_code==422

def test_parent_mapping_change_cannot_break_existing_child_hierarchy(structure_client):
    client, _db=structure_client
    workshop=post(client,"workshops",code="W-PARENT-CHANGE",description="Workshop",oracle_work_area_code="439")
    machine=post(client,"subworkshops",workshop_id=workshop["id"],code="S-PARENT-CHANGE",description="Machine",oracle_machine_code="4391")
    invalid=client.put(f"/api/v1/admin/structure/workshops/{workshop['id']}",json={"code":workshop["code"],"description":workshop["description"],"active":True,"oracle_work_area_code":None})
    assert invalid.status_code==409
    cell=post(client,"project-lines",subworkshop_id=machine["id"],code="P-PARENT-CHANGE",description="Cell",oracle_cell_code="54Q")
    changed=client.put(f"/api/v1/admin/structure/subworkshops/{machine['id']}",json={"workshop_id":workshop["id"],"code":machine["code"],"description":machine["description"],"active":True,"oracle_machine_code":"4393"})
    assert changed.status_code==409
    unmapped=post(client,"subworkshops",workshop_id=workshop["id"],code="S-UNMAPPED",description="Unmapped")
    edited=client.put(f"/api/v1/admin/structure/subworkshops/{unmapped['id']}",json={"workshop_id":workshop["id"],"code":unmapped["code"],"description":"Still editable","active":True})
    assert edited.status_code==200
    assert cell["oracle_cell_code"]=="54Q"
    assert cell["oracle_cell_code"]=="54Q"

def test_unmapped_structure_keeps_local_capture_and_blocks_oracle_payload(structure_client):
    client, db = structure_client
    w = post(client,"workshops",code="LOCAL-W",description="Local Workshop")
    s = post(client,"subworkshops",workshop_id=w["id"],code="LOCAL-S",description="Local Subworkshop")
    p = post(client,"project-lines",subworkshop_id=s["id"],code="LOCAL-P",description="Local Project")
    for code,effect in [("IN","ENTER"),("OUT","EXIT")]:
        response=client.post("/api/v1/admin/actions",json={"code":code,"label":code,"supplier_device_event":code,"state_effect":effect,"oracle_payroll_time_type":"Workshop Entry ES" if effect=="ENTER" else None})
        assert response.status_code==201,response.text
    terminal=Terminal(code="UNMAPPED",name="Unmapped",external_device_id="UNMAPPED",factory_code="ARGANDA",project_line_id=p["id"],active=True)
    db.add(terminal);db.commit()
    action=db.scalar(select(Action).where(Action.code=="IN"))
    event=_create_event(db,terminal,action,"TEST",IdentificationMethod.KEYPAD)
    event.person_id="23703"
    errors=event.oracle_mapping_error
    assert (event.workshop_code,event.subworkshop_code,event.project_line_code)==("LOCAL-W","LOCAL-S","LOCAL-P")
    assert all(value is None for value in (event.oracle_work_area_code,event.oracle_machine_code,event.oracle_cell_code))
    assert "WORK_AREA" in errors and "MACHINE" in errors and "CELL" in errors
    with pytest.raises(Exception,match="mapping is missing"):
        OracleClient().build_payload(event)

def test_legacy_terminal_and_event_remain_readable(structure_client):
    client,db=structure_client
    t=Terminal(code="LEGACY",name="Legacy",external_device_id="LEGACY",factory_code="ARGANDA",oracle_attributes={"work_cell":"C","custom":"keep"},active=False)
    db.add(t);db.commit()
    row=next(x for x in client.get("/api/v1/admin/terminals").json() if x["code"]=="LEGACY")
    assert row["project_line_id"] is None
    assert row["oracle_attributes"]["custom"]=="keep"
