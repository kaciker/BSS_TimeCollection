from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.structure import Workshop, Subworkshop, ProjectLine
from app.models.terminal import Terminal

router = APIRouter(prefix="/api/v1/admin/structure", tags=["structure"])

class WorkshopInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    code: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=255)
    active: bool = True

class SubworkshopInput(WorkshopInput):
    workshop_id: int = Field(gt=0)

class ProjectLineInput(WorkshopInput):
    subworkshop_id: int = Field(gt=0)

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
    if isinstance(row, Subworkshop): result["workshop_id"] = row.workshop_id
    if isinstance(row, ProjectLine):
        result["subworkshop_id"] = row.subworkshop_id
        result["workshop_id"] = row.subworkshop.workshop_id
    return result

@router.get("")
def list_structure(db: Session = Depends(get_db)):
    return {
        "workshops": [_read(row) for row in db.scalars(select(Workshop).order_by(Workshop.code))],
        "subworkshops": [_read(row) for row in db.scalars(select(Subworkshop).order_by(Subworkshop.workshop_id, Subworkshop.code))],
        "project_lines": [_read(row) for row in db.scalars(select(ProjectLine).order_by(ProjectLine.subworkshop_id, ProjectLine.code))],
    }

def _parent(db: Session, model, id: int):
    row = db.get(model, id)
    if row is None: raise HTTPException(404, "Parent not found")
    return row

def _edit(db: Session, model, id: int, values: dict):
    row = db.get(model, id)
    if row is None: raise HTTPException(404, "Structure record not found")
    if model is Subworkshop:
        parent = _parent(db, Workshop, values["workshop_id"])
        if not parent.active and values["active"]: raise HTTPException(409, "Parent Workshop is inactive")
    if model is ProjectLine:
        parent = _parent(db, Subworkshop, values["subworkshop_id"])
        if values["active"] and (not parent.active or not parent.workshop.active): raise HTTPException(409, "Parent path is inactive")
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
    return _read(_save(db, row))

@router.post("/workshops", status_code=201)
def create_workshop(payload: WorkshopInput, db: Session = Depends(get_db)):
    return _read(_save(db, Workshop(**payload.model_dump())))

@router.put("/workshops/{id}")
def update_workshop(id: int, payload: WorkshopInput, db: Session = Depends(get_db)):
    return _edit(db, Workshop, id, payload.model_dump())

@router.post("/subworkshops", status_code=201)
def create_subworkshop(payload: SubworkshopInput, db: Session = Depends(get_db)):
    parent = _parent(db, Workshop, payload.workshop_id)
    if payload.active and not parent.active: raise HTTPException(409, "Parent Workshop is inactive")
    return _read(_save(db, Subworkshop(**payload.model_dump())))

@router.put("/subworkshops/{id}")
def update_subworkshop(id: int, payload: SubworkshopInput, db: Session = Depends(get_db)):
    return _edit(db, Subworkshop, id, payload.model_dump())

@router.post("/project-lines", status_code=201)
def create_project_line(payload: ProjectLineInput, db: Session = Depends(get_db)):
    parent = _parent(db, Subworkshop, payload.subworkshop_id)
    if payload.active and (not parent.active or not parent.workshop.active): raise HTTPException(409, "Parent path is inactive")
    return _read(_save(db, ProjectLine(**payload.model_dump())))

@router.put("/project-lines/{id}")
def update_project_line(id: int, payload: ProjectLineInput, db: Session = Depends(get_db)):
    return _edit(db, ProjectLine, id, payload.model_dump())
