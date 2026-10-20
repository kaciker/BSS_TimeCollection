"""Perimeter presence, factory-local policy, and future external adapters."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo
from app.core.config import settings

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.action import Action
from app.models.perimeter import FactoryPerimeterEvent, FactoryPerimeterSettings, TerminalBadgeRead
from app.models.terminal import Terminal
from app.models.time_event import TimeEvent
from app.services.state_service import derive_worker_state


def settings_for(db: Session, factory_code: str) -> FactoryPerimeterSettings:
    return db.get(FactoryPerimeterSettings, factory_code) or FactoryPerimeterSettings(factory_code=factory_code, enabled=False, badge_source='OPEN', dedup_enabled=False, dedup_seconds=5, auto_exit_action_code=None)


def is_inside(db: Session, factory_code: str, badge: str) -> bool:
    last = db.scalar(select(FactoryPerimeterEvent).where(
        FactoryPerimeterEvent.factory_code == factory_code,
        FactoryPerimeterEvent.reporter_id == badge,
    ).order_by(FactoryPerimeterEvent.event_datetime.desc(), FactoryPerimeterEvent.id.desc()).limit(1))
    return last is not None and last.direction == "ENTER"


def check_badge_source(config: FactoryPerimeterSettings, badge: str) -> None:
    # The external adapter is intentionally unavailable until a plant integration is validated.
    if config.badge_source != "OPEN":
        raise HTTPException(503, "External badge validator is not configured")


def is_duplicate(db: Session, config: FactoryPerimeterSettings, terminal: Terminal, badge: str, now: datetime) -> bool:
    if not config.dedup_enabled or config.dedup_seconds <= 0:
        return False
    previous = db.get(TerminalBadgeRead, (terminal.factory_code, terminal.id, badge))
    if previous is None:
        return False
    timestamp = previous.last_recorded_at
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return now - timestamp < timedelta(seconds=config.dedup_seconds)


def remember_read(db: Session, terminal: Terminal, badge: str, now: datetime) -> None:
    key = (terminal.factory_code, terminal.id, badge)
    previous = db.get(TerminalBadgeRead, key)
    if previous is None:
        db.add(TerminalBadgeRead(factory_code=terminal.factory_code, terminal_id=terminal.id, reporter_id=badge, last_recorded_at=now))
    else:
        previous.last_recorded_at = now


def perimeter_scan(db: Session, terminal: Terminal, badge: str, method) -> dict:
    from app.services.event_service import _create_event
    from app.domain.enums import WorkerState
    from app.services.event_service import _lock_badge
    _lock_badge(db, badge)
    config = settings_for(db, terminal.factory_code)
    if not config.enabled:
        raise HTTPException(409, "Factory perimeter control is disabled")
    check_badge_source(config, badge)
    now = datetime.now(timezone.utc)
    event_time = now.astimezone(ZoneInfo(settings.event_timezone))
    inside = is_inside(db, terminal.factory_code, badge)
    role = terminal.terminal_role
    if role == "PERIMETER_ENTER":
        direction = "ENTER"
    elif role == "PERIMETER_EXIT":
        direction = "EXIT"
    else:
        direction = "EXIT" if inside else "ENTER"
    # Dedicated exit readers bypass cooldown while inside. Bidirectional
    # readers cannot distinguish a repeated read from a physical exit.
    if is_duplicate(db, config, terminal, badge, now) and not (role == "PERIMETER_EXIT" and inside):
        return {"flow": "DUPLICATE_IGNORED", "worker_state": WorkerState.INSIDE.value if inside else WorkerState.OUTSIDE.value}
    if direction == "ENTER" and inside:
        return {"flow": "ALREADY_INSIDE", "worker_state": WorkerState.INSIDE.value}
    if direction == "EXIT" and not inside:
        return {"flow": "ALREADY_OUTSIDE", "worker_state": WorkerState.OUTSIDE.value}
    correlation_id = str(uuid4())
    auto_event = None
    if direction == "EXIT" and derive_worker_state(db, badge, terminal.factory_code) == WorkerState.INSIDE:
        if not config.auto_exit_action_code:
            raise HTTPException(409, "Configure an automatic cell exit action before using the perimeter")
        action = db.scalar(select(Action).where(
            Action.code == config.auto_exit_action_code,
            Action.active.is_(True), Action.state_effect == "EXIT",
            Action.requires_subaction.is_(False),
        ))
        last_cell = db.scalar(select(TimeEvent).join(Terminal, TimeEvent.terminal_id == Terminal.id).where(TimeEvent.reporter_id == badge, Terminal.factory_code == terminal.factory_code, TimeEvent.state_effect == "ENTER").order_by(
            TimeEvent.event_datetime.desc(), TimeEvent.created_at.desc(), TimeEvent.id.desc()).limit(1))
        if action is None or last_cell is None:
            raise HTTPException(409, "Automatic exit action or original cell event unavailable")
        cell_terminal = db.get(Terminal, last_cell.terminal_id)
        if cell_terminal is None or cell_terminal.factory_code != terminal.factory_code:
            raise HTTPException(409, "Cannot safely determine the cell for automatic exit")
        auto_event = _create_event(db, cell_terminal, action, badge, method, commit=False, event_time=event_time, correlation_id=correlation_id, snapshot=last_cell)
        # Flush the cell EXIT first: the local movement has an FK to it.
        db.flush()
    db.add(FactoryPerimeterEvent(
        id=str(uuid4()), factory_code=terminal.factory_code, reporter_id=badge,
        terminal_id=terminal.id, direction=direction, event_datetime=event_time,
        correlation_id=correlation_id, auto_cell_exit_event_id=auto_event.id if auto_event else None,
    ))
    remember_read(db, terminal, badge, now)
    db.commit()
    return {"flow": "FACTORY_ENTRY_RECORDED" if direction == "ENTER" else "FACTORY_EXIT_RECORDED",
            "worker_state": WorkerState.INSIDE.value if direction == "ENTER" else WorkerState.OUTSIDE.value,
            "event": None}
