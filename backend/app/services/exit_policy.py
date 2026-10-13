"""Terminal exit restriction policy, independent of Oracle attendance validation."""
from fastapi import HTTPException
from sqlalchemy import func, select, literal_column
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.models.exit_policy import policies
from sqlalchemy.orm import Session

MODES = {"DISABLED", "SAME_TERMINAL", "SAME_WORK_CELL"}
INHERIT = "INHERIT"


def get_mode(db: Session, terminal_id: int | None) -> str:
    if terminal_id is not None:
        override = db.execute(select(policies.c.mode).where(policies.c.terminal_id == terminal_id)).scalar_one_or_none()
        if override is not None:
            return override
    return db.execute(select(policies.c.mode).where(policies.c.terminal_id.is_(None))).scalar_one_or_none() or "DISABLED"


def save_mode(db: Session, terminal_id: int | None, mode: str, *, commit: bool = True) -> None:
    if mode not in MODES | ({INHERIT} if terminal_id is not None else set()):
        raise HTTPException(422, "Invalid policy mode")
    if mode == INHERIT:
        db.execute(policies.delete().where(policies.c.terminal_id == terminal_id))
    else:
        insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
        statement = insert(policies).values(terminal_id=terminal_id, mode=mode)
        db.execute(statement.on_conflict_do_update(
            index_elements=[func.coalesce(policies.c.terminal_id, literal_column("0"))],
            set_={"mode": statement.excluded.mode},
        ))
    if commit:
        db.commit()


def work_cell(terminal) -> str | None:
    value = (terminal.oracle_attributes or {}).get("work_cell") if terminal else None
    return value.strip() if isinstance(value, str) and 0 < len(value.strip()) <= 64 else None


def check_exit_policy(db: Session, terminal, reporter_id: str) -> None:
    from app.models.time_event import TimeEvent
    mode = get_mode(db, terminal.id)
    if mode == "DISABLED":
        return
    last_entry = db.scalar(select(TimeEvent).where(
        TimeEvent.reporter_id == reporter_id, TimeEvent.state_effect == "ENTER"
    ).order_by(TimeEvent.event_datetime.desc(), TimeEvent.created_at.desc(), TimeEvent.id.desc()).limit(1))
    if last_entry is None:
        raise HTTPException(409, "No entry event found for terminal policy validation")
    if mode == "SAME_TERMINAL" and last_entry.terminal_id != terminal.id:
        raise HTTPException(409, f"Exit rejected: use entry terminal {last_entry.terminal_code}. No exit was recorded.")
    if mode == "SAME_WORK_CELL":
        from app.models.terminal import Terminal
        origin = db.get(Terminal, last_entry.terminal_id)
        origin_cell = work_cell(origin)
        current_cell = work_cell(terminal)
        if not origin_cell or not current_cell:
            raise HTTPException(409, f"Exit rejected: a work cell must be configured for both {last_entry.terminal_code} and {terminal.code}. Contact an administrator. No exit was recorded.")
        if origin_cell != current_cell:
            raise HTTPException(409, f"Exit rejected: use a terminal in entry work cell {origin_cell} (entry terminal {last_entry.terminal_code}). No exit was recorded.")
