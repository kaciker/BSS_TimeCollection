"""Perimeter presence, factory-local policy, and external adapters."""
from datetime import datetime, timedelta, timezone
import logging
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.enums import IdentificationMethod
from app.models.action import Action
from app.models.perimeter import FactoryPerimeterEvent, FactoryPerimeterSettings, TerminalBadgeRead
from app.models.terminal import Terminal
from app.models.time_event import TimeEvent

logger = logging.getLogger(__name__)


def settings_for(db: Session, factory_code: str) -> FactoryPerimeterSettings:
    return db.get(FactoryPerimeterSettings, factory_code) or FactoryPerimeterSettings(
        factory_code=factory_code,
        enabled=False,
        badge_source="OPEN",
        dedup_enabled=False,
        dedup_seconds=5,
        auto_exit_action_code=None,
    )


def is_inside(db: Session, factory_code: str, badge: str) -> bool:
    last = db.scalar(
        select(FactoryPerimeterEvent)
        .where(
            FactoryPerimeterEvent.factory_code == factory_code,
            FactoryPerimeterEvent.reporter_id == badge,
        )
        .order_by(FactoryPerimeterEvent.event_datetime.desc(), FactoryPerimeterEvent.id.desc())
        .limit(1)
    )
    return last is not None and last.direction == "ENTER"


def check_badge_source(config: FactoryPerimeterSettings, badge: str) -> None:
    if config.badge_source == "EXTERNAL":
        from app.services.external_perimeter import check_external_presence

        result = check_external_presence(badge)
        if result["status"] != "INSIDE":
            detail = "External perimeter presence: " + result["status"]
            if result.get("error_category"):
                detail += " (" + result["error_category"] + ")"
            raise HTTPException(503 if result["status"] == "ERROR" else 409, detail)
    elif config.badge_source != "OPEN":
        raise HTTPException(503, "Badge validator is not configured")


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
        db.add(
            TerminalBadgeRead(
                factory_code=terminal.factory_code,
                terminal_id=terminal.id,
                reporter_id=badge,
                last_recorded_at=now,
            )
        )
    else:
        previous.last_recorded_at = now


def create_auto_cell_exit_for_factory_exit(
    db: Session,
    config: FactoryPerimeterSettings,
    factory_code: str,
    badge: str,
    method,
    event_time: datetime,
    correlation_id: str,
    *,
    strict: bool = True,
) -> TimeEvent | None:
    """Close the active cell using stable person identity when it is resolvable."""
    from app.services.event_service import _create_event
    from app.services.person_identity import (
        PersonIdentityError,
        observe_identity,
        resolve_person_identity,
    )

    identity = None
    if config.badge_source == "EXTERNAL" and method == IdentificationMethod.RFID:
        try:
            identity = resolve_person_identity(badge)
            observe_identity(db, factory_code, identity, observed_at=event_time)
        except PersonIdentityError as exc:
            logger.warning(
                "External factory exit identity unresolved category=%s",
                exc.category,
            )

    identity_condition = TimeEvent.reporter_id == badge
    if identity is not None:
        identity_condition = or_(
            TimeEvent.person_id == identity.person_id,
            and_(TimeEvent.person_id.is_(None), TimeEvent.reporter_id == badge),
        )
    last_cell = db.scalar(
        select(TimeEvent)
        .join(Terminal, TimeEvent.terminal_id == Terminal.id)
        .where(
            identity_condition,
            Terminal.factory_code == factory_code,
            TimeEvent.state_effect.in_(["ENTER", "EXIT"]),
        )
        .order_by(TimeEvent.event_datetime.desc(), TimeEvent.created_at.desc(), TimeEvent.id.desc())
        .limit(1)
    )
    if last_cell is None or last_cell.state_effect != "ENTER":
        return None

    cell_time = last_cell.event_datetime
    if cell_time.tzinfo is None:
        cell_time = cell_time.replace(tzinfo=ZoneInfo(settings.event_timezone))
    exit_time = event_time
    if exit_time.tzinfo is None:
        exit_time = exit_time.replace(tzinfo=ZoneInfo(settings.event_timezone))
    if exit_time.astimezone(timezone.utc) < cell_time.astimezone(timezone.utc):
        return None

    if not config.auto_exit_action_code:
        if strict:
            raise HTTPException(409, "Configure an automatic cell exit action before using the perimeter")
        return None

    action = db.scalar(
        select(Action).where(
            Action.code == config.auto_exit_action_code,
            Action.active.is_(True),
            Action.state_effect == "EXIT",
            Action.requires_subaction.is_(False),
        )
    )
    cell_terminal = db.get(Terminal, last_cell.terminal_id)
    if action is None or cell_terminal is None or cell_terminal.factory_code != factory_code:
        if strict:
            raise HTTPException(409, "Automatic exit action or original cell event unavailable")
        return None

    return _create_event(
        db,
        cell_terminal,
        action,
        badge,
        method,
        commit=False,
        event_time=exit_time,
        correlation_id=correlation_id,
        snapshot=last_cell,
        identity=identity,
    )


def perimeter_scan(db: Session, terminal: Terminal, badge: str, method) -> dict:
    from app.domain.enums import WorkerState
    from app.services.event_service import _lock_badge

    _lock_badge(db, badge)
    config = settings_for(db, terminal.factory_code)
    if not config.enabled:
        raise HTTPException(409, "Factory perimeter control is disabled")
    if config.badge_source == "EXTERNAL":
        raise HTTPException(409, "External perimeter uses the existing factory readers; BSS perimeter terminals are not authoritative")
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

    if is_duplicate(db, config, terminal, badge, now) and not (role == "PERIMETER_EXIT" and inside):
        return {
            "flow": "DUPLICATE_IGNORED",
            "worker_state": WorkerState.INSIDE.value if inside else WorkerState.OUTSIDE.value,
        }
    if direction == "ENTER" and inside:
        return {"flow": "ALREADY_INSIDE", "worker_state": WorkerState.INSIDE.value}
    if direction == "EXIT" and not inside:
        return {"flow": "ALREADY_OUTSIDE", "worker_state": WorkerState.OUTSIDE.value}

    correlation_id = str(uuid4())
    auto_event = None
    if direction == "EXIT":
        auto_event = create_auto_cell_exit_for_factory_exit(
            db,
            config,
            terminal.factory_code,
            badge,
            method,
            event_time,
            correlation_id,
            strict=True,
        )
        if auto_event is not None:
            db.flush()

    db.add(
        FactoryPerimeterEvent(
            id=str(uuid4()),
            factory_code=terminal.factory_code,
            reporter_id=badge,
            terminal_id=terminal.id,
            direction=direction,
            event_datetime=event_time,
            correlation_id=correlation_id,
            auto_cell_exit_event_id=auto_event.id if auto_event else None,
        )
    )
    remember_read(db, terminal, badge, now)
    db.commit()
    return {
        "flow": "FACTORY_ENTRY_RECORDED" if direction == "ENTER" else "FACTORY_EXIT_RECORDED",
        "worker_state": WorkerState.INSIDE.value if direction == "ENTER" else WorkerState.OUTSIDE.value,
        "event": None,
    }
