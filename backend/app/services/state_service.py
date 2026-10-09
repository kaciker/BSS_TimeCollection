from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import StateEffect, WorkerState
from app.models.time_event import TimeEvent


def derive_worker_state(db: Session, reporter_id: str) -> WorkerState:
    event = db.scalar(
        select(TimeEvent)
        .where(TimeEvent.reporter_id == reporter_id)
        .where(TimeEvent.state_effect.in_([StateEffect.ENTER.value, StateEffect.EXIT.value]))
        .order_by(TimeEvent.event_datetime.desc(), TimeEvent.created_at.desc())
        .limit(1)
    )
    if event is None or event.state_effect == StateEffect.EXIT.value:
        return WorkerState.OUTSIDE
    return WorkerState.INSIDE
