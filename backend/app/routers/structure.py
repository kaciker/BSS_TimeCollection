from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.structure import Workshop, Subworkshop, ProjectLine
from app.models.terminal import Terminal
from app.models.oracle_catalogue import OracleCell, OracleMachine, OraclePayrollTimeType, OracleWorkArea
from app.services.oracle_catalogue import catalogue_payload, structure_mapping_errors, structure_parent_mapping_errors

router = APIRouter(prefix="/api/v1/admin/structure", tags=["structure"])

class StructureInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    code: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=255)
    active: bool = True

class WorkshopInput(StructureInput):
    oracle_work_area_code: str | None = Field(default=None, max_length=80)

class SubworkshopInput(StructureInput):
    workshop_id: int = Field(gt=0)
    oracle_machine_code: str | None = Field(default=None, max_length=80)

class ProjectLineInput(StructureInput):
    subworkshop_id: int = Field(gt=0)
    oracle_cell_code: str | None = Field(default=None, max_length=80)

class CatalogueValueInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    code: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=255)
    parent_code: str | None = Field(default=None, max_length=80)
    source_reference: str | None = Field(default=None, max_length=255)
    active: bool = True

class CatalogueImportInput(BaseModel):
    """Canonical converted HR-Path JSON format; import is additive/upsert only."""
    work_areas: list[dict]
    machines: list[dict]
    cells: list[dict]
    payroll_time_types: list[dict]

def _save(db: Session, row):
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Code already exists within this parent")
    return row

def _read(row):
    result = {"id": row.id, "code": row.code, "description": row.description, "active": row.active}
    if isinstance(row, Workshop): result["oracle_work_area_code"] = row.oracle_work_area_code
    if isinstance(row, Subworkshop): result["workshop_id"] = row.workshop_id
    if isinstance(row, Subworkshop): result["oracle_machine_code"] = row.oracle_machine_code
    if isinstance(row, ProjectLine):
        result["subworkshop_id"] = row.subworkshop_id
        result["workshop_id"] = row.subworkshop.workshop_id
        result["oracle_cell_code"] = row.oracle_cell_code
    return result

@router.get("")
def list_structure(db: Session = Depends(get_db)):
    return {
        "workshops": [_read(row) for row in db.scalars(select(Workshop).order_by(Workshop.code))],
        "subworkshops": [_read(row) for row in db.scalars(select(Subworkshop).order_by(Subworkshop.workshop_id, Subworkshop.code))],
        "project_lines": [_read(row) for row in db.scalars(select(ProjectLine).order_by(ProjectLine.subworkshop_id, ProjectLine.code))],
    }

@router.get("/oracle-catalogue")
def oracle_catalogue(db: Session = Depends(get_db)):
    return catalogue_payload(db)

@router.get("/oracle-catalogue/admin")
def oracle_catalogue_admin(db: Session = Depends(get_db)):
    return catalogue_payload(db, include_inactive=True)

def _save_catalogue_row(db: Session, model, values: dict, *, parent_model=None, parent_field: str | None = None):
    values = dict(values)
    code = values["code"].strip()
    parent_code = values.pop("parent_code", None)
    if parent_model is not None:
        parent = db.get(parent_model, parent_code) if parent_code else None
        if parent is None or not parent.active:
            raise HTTPException(422, "Select an existing active Oracle parent catalogue value")
    row = db.get(model, code)
    if row is None:
        row = model(code=code)
        db.add(row)
    for key in ("description", "active", "source_reference"):
        if key in values:
            setattr(row, key, values[key])
    if parent_field:
        setattr(row, parent_field, parent_code)
    return row

def _catalogue_upsert(db: Session, model, payload: CatalogueValueInput, *, parent_model=None, parent_field: str | None = None):
    values = payload.model_dump()
    if model is OraclePayrollTimeType:
        values["description"] = values.get("description")
    else:
        values["description"] = values.get("description") or ""
    row = _save_catalogue_row(db, model, values, parent_model=parent_model, parent_field=parent_field)
    try:
        db.commit()
        db.refresh(row)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Catalogue code or parent reference conflicts")
    return {"code": row.code, "description": row.description, "active": row.active}

@router.post("/oracle-catalogue/work-areas", status_code=201)
def create_oracle_work_area(payload: CatalogueValueInput, db: Session = Depends(get_db)):
    return _catalogue_upsert(db, OracleWorkArea, payload)

@router.post("/oracle-catalogue/machines", status_code=201)
def create_oracle_machine(payload: CatalogueValueInput, db: Session = Depends(get_db)):
    if not payload.description or not payload.parent_code:
        raise HTTPException(422, "MACHINE description and WORK_AREA parent are required")
    return _catalogue_upsert(db, OracleMachine, payload, parent_model=OracleWorkArea, parent_field="work_area_code")

@router.post("/oracle-catalogue/cells", status_code=201)
def create_oracle_cell(payload: CatalogueValueInput, db: Session = Depends(get_db)):
    if not payload.description or not payload.parent_code:
        raise HTTPException(422, "CELL description and MACHINE parent are required")
    return _catalogue_upsert(db, OracleCell, payload, parent_model=OracleMachine, parent_field="machine_code")

@router.post("/oracle-catalogue/payroll-time-types", status_code=201)
def create_oracle_payroll_time_type(payload: CatalogueValueInput, db: Session = Depends(get_db)):
    return _catalogue_upsert(db, OraclePayrollTimeType, payload)

@router.put("/oracle-catalogue/{kind}/{code}")
def update_oracle_catalogue(kind: str, code: str, payload: CatalogueValueInput, db: Session = Depends(get_db)):
    models = {"work-areas": (OracleWorkArea, None, None), "machines": (OracleMachine, OracleWorkArea, "work_area_code"), "cells": (OracleCell, OracleMachine, "machine_code"), "payroll-time-types": (OraclePayrollTimeType, None, None)}
    if kind not in models:
        raise HTTPException(404, "Unknown Oracle catalogue type")
    model, parent_model, parent_field = models[kind]
    if payload.code != code:
        raise HTTPException(422, "Catalogue codes are immutable; deactivate and add a replacement")
    row = db.get(model, code)
    if row is None:
        raise HTTPException(404, "Catalogue entry not found")
    values = payload.model_dump()
    values["description"] = values.get("description") or ""
    parent_code = values.pop("parent_code", None)
    if parent_field:
        parent = db.get(parent_model, parent_code) if parent_code else None
        if parent is None or not parent.active:
            raise HTTPException(422, "Select an active parent catalogue value")
        setattr(row, parent_field, parent_code)
    for key in ("description", "active", "source_reference"):
        if key in values:
            setattr(row, key, values[key])
    db.commit()
    return {"code": row.code, "description": row.description, "active": row.active}

@router.post("/oracle-catalogue/import")
def import_oracle_catalogue(payload: CatalogueImportInput, db: Session = Depends(get_db)):
    """Validate parent paths, then atomically upsert; omitted items are preserved."""
    errors: list[str] = []
    areas = {item.get("code") for item in payload.work_areas if item.get("code")}
    machines = {item.get("code") for item in payload.machines if item.get("code")}
    all_rows = payload.work_areas + payload.machines + payload.cells
    for item in all_rows:
        if not item.get("code") or not item.get("description"):
            errors.append(f"{item.get('code') or '<missing code>'}: code and description are required")
    for item in payload.payroll_time_types:
        if not item.get("code"):
            errors.append("PayrollTimeType: code is required")
    for label, items in (("WORK_AREA", payload.work_areas), ("MACHINE", payload.machines), ("CELL", payload.cells), ("PayrollTimeType", payload.payroll_time_types)):
        codes = [item.get("code") for item in items if item.get("code")]
        if len(codes) != len(set(codes)):
            errors.append(f"Duplicate {label} codes in import")
    for item in payload.machines:
        if item.get("work_area_code") not in areas and db.get(OracleWorkArea, item.get("work_area_code")) is None:
            errors.append(f"MACHINE {item.get('code')} references unknown WORK_AREA {item.get('work_area_code')}")
    for item in payload.cells:
        if item.get("machine_code") not in machines and db.get(OracleMachine, item.get("machine_code")) is None:
            errors.append(f"CELL {item.get('code')} references unknown MACHINE {item.get('machine_code')}")
    if errors:
        raise HTTPException(422, {"added": 0, "updated": 0, "unchanged": 0, "invalid": len(errors), "errors": errors})

    rows = []
    for values in payload.work_areas:
        rows.append((OracleWorkArea, values, None, None))
    for values in payload.machines:
        rows.append((OracleMachine, values, OracleWorkArea, "work_area_code"))
    for values in payload.cells:
        rows.append((OracleCell, values, OracleMachine, "machine_code"))
    for values in payload.payroll_time_types:
        rows.append((OraclePayrollTimeType, values, None, None))
    counts = {"added": 0, "updated": 0, "unchanged": 0, "invalid": 0}
    try:
        for model, values, parent_model, parent_field in rows:
            before = db.get(model, values.get("code"))
            parent_code = values.get(parent_field) if parent_field else None
            if before is not None and parent_field and getattr(before, parent_field) != parent_code:
                if model is OracleMachine and db.scalar(select(Workshop.id).where(Workshop.oracle_work_area_code == before.work_area_code).limit(1)) is not None:
                    raise ValueError(f"Cannot change MACHINE {before.code} parent while a Workshop maps to its current hierarchy")
                if model is OracleCell and db.scalar(select(ProjectLine.id).where(ProjectLine.oracle_cell_code == before.code).limit(1)) is not None:
                    raise ValueError(f"Cannot change CELL {before.code} parent while a Project / Line maps to it")
            old = ({column: getattr(before, column) for column in ("description", "active", "source_reference", parent_field) if column and hasattr(before, column)} if before else None)
            normalized = {"code": values.get("code"), "description": values.get("description") or "", "active": values.get("active", True), "source_reference": values.get("source_reference")}
            if parent_field:
                normalized["parent_code"] = values.get(parent_field)
            row = _save_catalogue_row(db, model, normalized, parent_model=parent_model, parent_field=parent_field)
            db.flush()
            new = {column: getattr(row, column) for column in old} if old is not None else None
            counts["added" if before is None else "unchanged" if old == new else "updated"] += 1
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(422, f"Catalogue import rejected; no changes committed: {exc}") from exc
    return counts

def _validate_oracle_mapping(db: Session, model, values: dict, parent=None):
    if model is Workshop:
        code = values.get("oracle_work_area_code")
        row = db.get(OracleWorkArea, code) if code is not None else None
        if code is not None and (row is None or not row.active):
            raise HTTPException(422, "Oracle WORK_AREA is missing or inactive in the HR-Path catalogue")
        return
    if model is Subworkshop:
        code = values.get("oracle_machine_code")
        if code is None:
            return
        if not parent.oracle_work_area_code:
            raise HTTPException(422, "Oracle MACHINE requires a mapped parent Workshop Oracle WORK_AREA")
        machine = db.get(OracleMachine, code)
        if machine is None or not machine.active:
            raise HTTPException(422, "Oracle MACHINE is missing or inactive in the HR-Path catalogue")
        if machine.work_area_code != parent.oracle_work_area_code:
            raise HTTPException(422, "Oracle MACHINE does not belong to parent WORK_AREA")
        return
    code = values.get("oracle_cell_code")
    if code is None:
        return
    if not parent.oracle_machine_code:
        raise HTTPException(422, "Oracle CELL requires a mapped parent Subworkshop Oracle MACHINE")
    parent_errors = structure_parent_mapping_errors(db,
        work_area=parent.workshop.oracle_work_area_code,
        machine=parent.oracle_machine_code,
    )
    if parent_errors:
        raise HTTPException(422, "; ".join(parent_errors))
    cell = db.get(OracleCell, code)
    if cell is None or not cell.active:
        raise HTTPException(422, "Oracle CELL is missing or inactive in the HR-Path catalogue")
    if cell.machine_code != parent.oracle_machine_code:
        raise HTTPException(422, "Oracle CELL does not belong to parent MACHINE")

def _parent(db: Session, model, id: int):
    row = db.get(model, id)
    if row is None: raise HTTPException(404, "Parent not found")
    return row

def _edit(db: Session, model, id: int, values: dict):
    row = db.get(model, id)
    if row is None: raise HTTPException(404, "Structure record not found")
    if model is Subworkshop:
        parent = _parent(db, Workshop, values["workshop_id"])
        _validate_oracle_mapping(db, model, values, parent)
        if not parent.active and values["active"]: raise HTTPException(409, "Parent Workshop is inactive")
    if model is ProjectLine:
        parent = _parent(db, Subworkshop, values["subworkshop_id"])
        _validate_oracle_mapping(db, model, values, parent)
        if values["active"] and (not parent.active or not parent.workshop.active): raise HTTPException(409, "Parent path is inactive")
    if model is Workshop:
        _validate_oracle_mapping(db, model, values)
    if row.active and not values["active"]:
        if model is Workshop and db.scalar(select(Subworkshop.id).where(Subworkshop.workshop_id == id, Subworkshop.active.is_(True)).limit(1)) is not None:
            raise HTTPException(409, "Deactivate active Subworkshops first")
        if model is Subworkshop and db.scalar(select(ProjectLine.id).where(ProjectLine.subworkshop_id == id, ProjectLine.active.is_(True)).limit(1)) is not None:
            raise HTTPException(409, "Deactivate active Project / Lines first")
        if model is ProjectLine and db.scalar(select(Terminal.id).where(Terminal.project_line_id == id, Terminal.active.is_(True), Terminal.deleted_at.is_(None)).limit(1)) is not None:
            raise HTTPException(409, "Assign active terminals to another Project / Line first")
    if model is Subworkshop and row.workshop_id != values["workshop_id"] and row.project_lines:
        raise HTTPException(409, "Cannot move a Subworkshop with Project / Lines")
    if model is ProjectLine and row.subworkshop_id != values["subworkshop_id"] and db.scalar(select(Terminal.id).where(Terminal.project_line_id == id).limit(1)) is not None:
        raise HTTPException(409, "Cannot move a Project / Line assigned to terminals")
    for key, value in values.items(): setattr(row, key, value)
    if model is Workshop:
        for child in row.subworkshops:
            if child.oracle_machine_code and structure_parent_mapping_errors(db,
                    work_area=row.oracle_work_area_code,
                    machine=child.oracle_machine_code,
                ):
                db.rollback()
                raise HTTPException(409, "Workshop Oracle WORK_AREA conflicts with an existing Subworkshop Oracle MACHINE mapping")
    if model is Subworkshop:
        for child in row.project_lines:
            if child.oracle_cell_code and structure_mapping_errors(db,
                    work_area=row.workshop.oracle_work_area_code,
                    machine=row.oracle_machine_code,
                    cell=child.oracle_cell_code,
                ):
                db.rollback()
                raise HTTPException(409, "Subworkshop Oracle MACHINE conflicts with an existing Project / Line Oracle CELL mapping")
    return _read(_save(db, row))

@router.post("/workshops", status_code=201)
def create_workshop(payload: WorkshopInput, db: Session = Depends(get_db)):
    _validate_oracle_mapping(db, Workshop, payload.model_dump())
    return _read(_save(db, Workshop(**payload.model_dump())))

@router.put("/workshops/{id}")
def update_workshop(id: int, payload: WorkshopInput, db: Session = Depends(get_db)):
    return _edit(db, Workshop, id, payload.model_dump())

@router.post("/subworkshops", status_code=201)
def create_subworkshop(payload: SubworkshopInput, db: Session = Depends(get_db)):
    parent = _parent(db, Workshop, payload.workshop_id)
    _validate_oracle_mapping(db, Subworkshop, payload.model_dump(), parent)
    if payload.active and not parent.active: raise HTTPException(409, "Parent Workshop is inactive")
    return _read(_save(db, Subworkshop(**payload.model_dump())))

@router.put("/subworkshops/{id}")
def update_subworkshop(id: int, payload: SubworkshopInput, db: Session = Depends(get_db)):
    return _edit(db, Subworkshop, id, payload.model_dump())

@router.post("/project-lines", status_code=201)
def create_project_line(payload: ProjectLineInput, db: Session = Depends(get_db)):
    parent = _parent(db, Subworkshop, payload.subworkshop_id)
    _validate_oracle_mapping(db, ProjectLine, payload.model_dump(), parent)
    if payload.active and (not parent.active or not parent.workshop.active): raise HTTPException(409, "Parent path is inactive")
    return _read(_save(db, ProjectLine(**payload.model_dump())))

@router.put("/project-lines/{id}")
def update_project_line(id: int, payload: ProjectLineInput, db: Session = Depends(get_db)):
    return _edit(db, ProjectLine, id, payload.model_dump())
