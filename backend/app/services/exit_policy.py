"""Terminal exit restriction policy, independent of Oracle attendance validation."""
from fastapi import HTTPException
from sqlalchemy import Column, Integer, MetaData, String, Table, select
from sqlalchemy.orm import Session

metadata = MetaData()
policies = Table("exit_policies", metadata,
    Column("id", Integer, primary_key=True),
    Column("terminal_id", Integer, nullable=True, unique=True),
    Column("mode", String(32), nullable=False),
)
MODES = {"DISABLED", "SAME_TERMINAL", "SAME_WORK_CELL"}
INHERIT = "INHERIT"


def ensure_policy_table(engine):
    metadata.create_all(engine, tables=[policies], checkfirst=True)


def get_mode(db: Session, terminal_id: int | None) -> str:
    if terminal_id is not None:
        override = db.execute(select(policies.c.mode).where(policies.c.terminal_id == terminal_id)).scalar_one_or_none()
        if override is not None:
            return override
    return db.execute(select(policies.c.mode).where(policies.c.terminal_id.is_(None))).scalar_one_or_none() or "DISABLED"


def save_mode(db: Session, terminal_id: int | None, mode: str) -> None:
    if mode not in MODES | ({INHERIT} if terminal_id is not None else set()):
        raise HTTPException(422, "Invalid policy mode")
    existing = db.execute(select(policies.c.id).where(policies.c.terminal_id == terminal_id)).scalar_one_or_none()
    if mode == INHERIT:
        if existing is not None:
            db.execute(policies.delete().where(policies.c.id == existing))
    elif existing is None:
        db.execute(policies.insert().values(terminal_id=terminal_id, mode=mode))
    else:
        db.execute(policies.update().where(policies.c.id == existing).values(mode=mode))
    db.commit()


def check_exit_policy(db: Session, terminal, reporter_id: str) -> None:
    from app.models.time_event import TimeEvent
    mode = get_mode(db, terminal.id)
    if mode == "DISABLED":
        return
    last_entry = db.scalar(select(TimeEvent).where(
        TimeEvent.reporter_id == reporter_id, TimeEvent.state_effect == "ENTER"
    ).order_by(TimeEvent.event_datetime.desc(), TimeEvent.created_at.desc()).limit(1))
    if last_entry is None:
        raise HTTPException(409, "No entry event found for terminal policy validation")
    if mode == "SAME_TERMINAL" and last_entry.terminal_id != terminal.id:
        raise HTTPException(409, "Exit must be registered at the terminal used for entry")
    if mode == "SAME_WORK_CELL":
        from app.models.terminal import Terminal
        origin = db.get(Terminal, last_entry.terminal_id)
        origin_cell = (origin.oracle_attributes or {}).get("work_cell") if origin else None
        current_cell = (terminal.oracle_attributes or {}).get("work_cell")
        if not origin_cell or not current_cell or origin_cell != current_cell:
            raise HTTPException(409, "Exit must be registered in the same configured work cell")
