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
from app.services.external_perimeter import connector_status, test_external_connection, check_external_presence

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


class ExternalBadgeTest(BaseModel):
    badge: str = Field(min_length=1, max_length=64)


def _external_factory(factory_code: str) -> None:
    if factory_code.upper() != "ARGANDA":
        raise HTTPException(404, "External perimeter is available only for ARGANDA")


@router.get("/{factory_code}/external/status")
def external_status(factory_code: str):
    _external_factory(factory_code)
    return connector_status()


@router.post("/{factory_code}/external/check")
def external_check(factory_code: str):
    _external_factory(factory_code)
    return test_external_connection()


@router.post("/{factory_code}/external/test-badge")
def external_test_badge(factory_code: str, payload: ExternalBadgeTest):
    _external_factory(factory_code)
    result = check_external_presence(payload.badge)
    return {
        "status": result.get("status", "ERROR"),
        "external_event_time": result.get("event_time"),
        "zone_code": result.get("zone_code"),
        "error_category": result.get("error_category"),
    }


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
    if payload.auto_exit_action_code:
        action = db.scalar(select(Action).where(Action.code == payload.auto_exit_action_code, Action.active.is_(True), Action.state_effect == 'EXIT', Action.requires_subaction.is_(False)))
        if action is None:
            raise HTTPException(422, 'Automatic cell EXIT action must exist, be active and not require subactions')
    if payload.badge_source == "EXTERNAL" and factory_code.upper() != "ARGANDA":
        raise HTTPException(422, "External SQL Server perimeter is configured only for ARGANDA")
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
    if payload.role == "CELL" and terminal.terminal_role != "CELL":
        from app.services.configuration_service import validate_actions
        validate_actions(terminal.actions, terminal.code)
        leaf = terminal.project_line
        if leaf is None or not leaf.active or not leaf.subworkshop.active or not leaf.subworkshop.workshop.active:
            raise HTTPException(422, "Configure cell structure and actions in Terminals before selecting the Cell role")
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
