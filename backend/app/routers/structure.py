from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.structure import Workshop, Subworkshop, ProjectLine
from app.models.terminal import Terminal
from app.services.oracle_catalogue import CELLS, MACHINES, PAYROLL_TIME_TYPES, WORK_AREAS
from app.services.oracle_readiness import structure_parent_mapping_errors

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
def oracle_catalogue():
    return {
        "payroll_time_types": list(PAYROLL_TIME_TYPES),
        "work_areas": [{"code": code, "description": label} for code, label in WORK_AREAS.items()],
        "machines": [{"code": code, **value} for code, value in MACHINES.items()],
        "cells": [{"code": code, **value} for code, value in CELLS.items()],
    }

def _validate_oracle_mapping(model, values: dict, parent=None):
    if model is Workshop:
        code = values.get("oracle_work_area_code")
        if code is not None and code not in WORK_AREAS:
            raise HTTPException(422, "Oracle WORK_AREA is not in the HR-Path catalogue")
        return
    if model is Subworkshop:
        code = values.get("oracle_machine_code")
        if code is None:
            return
        if not parent.oracle_work_area_code:
            raise HTTPException(422, "Oracle MACHINE requires a mapped parent Workshop Oracle WORK_AREA")
        if code not in MACHINES:
            raise HTTPException(422, "Oracle MACHINE is not in the HR-Path catalogue")
        if MACHINES[code]["work_area"] != parent.oracle_work_area_code:
            raise HTTPException(422, "Oracle MACHINE does not belong to parent WORK_AREA")
        return
    code = values.get("oracle_cell_code")
    if code is None:
        return
    if not parent.oracle_machine_code:
        raise HTTPException(422, "Oracle CELL requires a mapped parent Subworkshop Oracle MACHINE")
    parent_errors = structure_parent_mapping_errors(
        work_area=parent.workshop.oracle_work_area_code,
        machine=parent.oracle_machine_code,
    )
    if parent_errors:
        raise HTTPException(422, "; ".join(parent_errors))
    if code not in CELLS:
        raise HTTPException(422, "Oracle CELL is not in the HR-Path catalogue")
    if CELLS[code]["machine"] != parent.oracle_machine_code:
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
        _validate_oracle_mapping(model, values, parent)
        if not parent.active and values["active"]: raise HTTPException(409, "Parent Workshop is inactive")
    if model is ProjectLine:
        parent = _parent(db, Subworkshop, values["subworkshop_id"])
        _validate_oracle_mapping(model, values, parent)
        if values["active"] and (not parent.active or not parent.workshop.active): raise HTTPException(409, "Parent path is inactive")
    if model is Workshop:
        _validate_oracle_mapping(model, values)
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
            if child.oracle_machine_code and (child.oracle_machine_code not in MACHINES or MACHINES[child.oracle_machine_code]["work_area"] != row.oracle_work_area_code):
                db.rollback()
                raise HTTPException(409, "Workshop Oracle WORK_AREA conflicts with an existing Subworkshop Oracle MACHINE mapping")
    if model is Subworkshop:
        for child in row.project_lines:
            if child.oracle_cell_code and (child.oracle_cell_code not in CELLS or CELLS[child.oracle_cell_code]["machine"] != row.oracle_machine_code):
                db.rollback()
                raise HTTPException(409, "Subworkshop Oracle MACHINE conflicts with an existing Project / Line Oracle CELL mapping")
        parent_errors = structure_parent_mapping_errors(
            work_area=row.workshop.oracle_work_area_code,
            machine=row.oracle_machine_code,
        )
        if parent_errors:
            db.rollback()
            raise HTTPException(409, "; ".join(parent_errors))
    return _read(_save(db, row))

@router.post("/workshops", status_code=201)
def create_workshop(payload: WorkshopInput, db: Session = Depends(get_db)):
    _validate_oracle_mapping(Workshop, payload.model_dump())
    return _read(_save(db, Workshop(**payload.model_dump())))

@router.put("/workshops/{id}")
def update_workshop(id: int, payload: WorkshopInput, db: Session = Depends(get_db)):
    return _edit(db, Workshop, id, payload.model_dump())

@router.post("/subworkshops", status_code=201)
def create_subworkshop(payload: SubworkshopInput, db: Session = Depends(get_db)):
    parent = _parent(db, Workshop, payload.workshop_id)
    _validate_oracle_mapping(Subworkshop, payload.model_dump(), parent)
    if payload.active and not parent.active: raise HTTPException(409, "Parent Workshop is inactive")
    return _read(_save(db, Subworkshop(**payload.model_dump())))

@router.put("/subworkshops/{id}")
def update_subworkshop(id: int, payload: SubworkshopInput, db: Session = Depends(get_db)):
    return _edit(db, Subworkshop, id, payload.model_dump())

@router.post("/project-lines", status_code=201)
def create_project_line(payload: ProjectLineInput, db: Session = Depends(get_db)):
    parent = _parent(db, Subworkshop, payload.subworkshop_id)
    _validate_oracle_mapping(ProjectLine, payload.model_dump(), parent)
    if payload.active and (not parent.active or not parent.workshop.active): raise HTTPException(409, "Parent path is inactive")
    return _read(_save(db, ProjectLine(**payload.model_dump())))

@router.put("/project-lines/{id}")
def update_project_line(id: int, payload: ProjectLineInput, db: Session = Depends(get_db)):
    return _edit(db, ProjectLine, id, payload.model_dump())
