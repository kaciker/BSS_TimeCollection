"""Administrative configuration and audit of factory presence."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.perimeter import FactoryPerimeterEvent, FactoryPerimeterSettings
from app.models.terminal import Terminal
from app.models.action import Action
from app.services.perimeter_service import settings_for, is_inside

router = APIRouter(prefix="/api/v1/admin/perimeter", tags=["perimeter"])


class FactoryConfigUpdate(BaseModel):
    enabled: bool = False
    badge_source: Literal["OPEN", "EXTERNAL"] = "OPEN"
    dedup_enabled: bool = True
    dedup_seconds: int = Field(default=5, ge=0, le=300)
    auto_exit_action_code: str | None = None


class TerminalRoleUpdate(BaseModel):
    role: Literal["CELL", "PERIMETER_ENTER", "PERIMETER_EXIT", "PERIMETER_BOTH"]
    factory_code: str = Field(min_length=1, max_length=64)


@router.get("/{factory_code}")
def get_config(factory_code: str, db: Session = Depends(get_db)):
    c = settings_for(db, factory_code)
    return {"factory_code": factory_code, "enabled": c.enabled, "badge_source": c.badge_source,
            "dedup_enabled": c.dedup_enabled, "dedup_seconds": c.dedup_seconds,
            "auto_exit_action_code": c.auto_exit_action_code}


@router.put("/{factory_code}")
def set_config(factory_code: str, payload: FactoryConfigUpdate, db: Session = Depends(get_db)):
    if payload.enabled and not payload.auto_exit_action_code:
        raise HTTPException(422, 'Configure the automatic cell EXIT action before enabling perimeter control')
    if payload.enabled:
        action = db.scalar(select(Action).where(Action.code == payload.auto_exit_action_code, Action.active.is_(True), Action.state_effect == 'EXIT', Action.requires_subaction.is_(False)))
        if action is None:
            raise HTTPException(422, 'Automatic cell EXIT action must exist, be active and not require subactions')
    if payload.badge_source == "EXTERNAL":
        raise HTTPException(422, "External badge source is not yet implemented")
    c = db.get(FactoryPerimeterSettings, factory_code)
    if c is None:
        c = FactoryPerimeterSettings(factory_code=factory_code)
        db.add(c)
    for field, value in payload.model_dump().items():
        setattr(c, field, value)
    db.commit()
    return get_config(factory_code, db)


@router.put("/terminals/{terminal_code}/role")
def set_terminal_role(terminal_code: str, payload: TerminalRoleUpdate, db: Session = Depends(get_db)):
    terminal = db.scalar(select(Terminal).where(Terminal.code == terminal_code, Terminal.deleted_at.is_(None)).with_for_update())
    if terminal is None:
        raise HTTPException(404, "Terminal not found")
    terminal.factory_code = payload.factory_code
    terminal.terminal_role = payload.role
    db.commit()
    return {"code": terminal.code, "factory_code": terminal.factory_code, "role": terminal.terminal_role}


@router.get("/{factory_code}/presence")
def presence(factory_code: str, limit: int = Query(200, ge=1, le=1000), db: Session = Depends(get_db)):
    rows = db.scalars(select(FactoryPerimeterEvent).where(
        FactoryPerimeterEvent.factory_code == factory_code,
    ).order_by(FactoryPerimeterEvent.event_datetime.desc()).limit(limit)).all()
    badges = db.scalars(select(FactoryPerimeterEvent.reporter_id).where(
        FactoryPerimeterEvent.factory_code == factory_code).distinct()).all()
    return {"factory_code": factory_code, "inside": [badge for badge in badges if is_inside(db, factory_code, badge)],
            "recent_events": [{"id": row.id, "badge": row.reporter_id, "direction": row.direction,
                               "at": row.event_datetime, "correlation_id": row.correlation_id,
                               "auto_cell_exit_event_id": row.auto_cell_exit_event_id} for row in rows]}
