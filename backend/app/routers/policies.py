"""Administration API for exit policies."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.terminal import Terminal
from app.services.exit_policy import get_mode, save_mode, policies, work_cell

router = APIRouter(prefix="/api/v1/admin/policies", tags=["policies"])


class PolicyUpdate(BaseModel):
    mode: Literal["DISABLED", "SAME_TERMINAL", "SAME_WORK_CELL", "INHERIT"]


class WorkCellUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    work_cell: str = Field(strict=True, max_length=64)


@router.get("/same-terminal-exit")
def read_policy(db: Session = Depends(get_db)):
    global_mode = get_mode(db, None)
    overrides = {r.terminal_id: r.mode for r in db.execute(select(policies.c.terminal_id, policies.c.mode)).all() if r.terminal_id is not None}
    terminals = db.scalars(select(Terminal).where(Terminal.deleted_at.is_(None)).order_by(Terminal.code)).all()
    return {"global_mode": global_mode, "terminals": [
        {"code": t.code, "name": t.name, "mode": overrides.get(t.id, "INHERIT"), "effective_mode": get_mode(db, t.id),
         "work_cell": work_cell(t)}
        for t in terminals]}


@router.put("/same-terminal-exit")
def update_global(payload: PolicyUpdate, db: Session = Depends(get_db)):
    if payload.mode == "INHERIT":
        raise HTTPException(422, "Global policy cannot inherit")
    save_mode(db, None, payload.mode)
    return {"mode": payload.mode}


@router.put("/same-terminal-exit/terminals/{terminal_code}")
def update_terminal(terminal_code: str, payload: PolicyUpdate, db: Session = Depends(get_db)):
    terminal = db.scalar(select(Terminal).where(Terminal.code == terminal_code, Terminal.deleted_at.is_(None)))
    if terminal is None:
        raise HTTPException(404, "Terminal not found")
    save_mode(db, terminal.id, payload.mode)
    return {"code": terminal.code, "mode": payload.mode, "effective_mode": get_mode(db, terminal.id)}


@router.put("/same-terminal-exit/terminals/{terminal_code}/work-cell")
def update_work_cell(terminal_code: str, payload: WorkCellUpdate, db: Session = Depends(get_db)):
    terminal = db.scalar(select(Terminal).where(Terminal.code == terminal_code, Terminal.deleted_at.is_(None)).with_for_update())
    if terminal is None:
        raise HTTPException(404, "Terminal not found")
    attributes = dict(terminal.oracle_attributes or {})
    if payload.work_cell:
        attributes["work_cell"] = payload.work_cell
    else:
        attributes.pop("work_cell", None)
    terminal.oracle_attributes = attributes
    db.commit()
    return {"code": terminal.code, "work_cell": work_cell(terminal)}
