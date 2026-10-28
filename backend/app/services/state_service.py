from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.domain.enums import StateEffect, WorkerState
from app.models.time_event import TimeEvent


def _identity_condition(reporter_id: str, person_id: str | None):
    if person_id:
        return or_(
            TimeEvent.person_id == person_id,
            and_(TimeEvent.person_id.is_(None), TimeEvent.reporter_id == reporter_id),
        )
    return TimeEvent.reporter_id == reporter_id


def derive_worker_state(
    db: Session,
    reporter_id: str,
    factory_code: str | None = None,
    *,
    person_id: str | None = None,
) -> WorkerState:
    from app.models.terminal import Terminal

    query = select(TimeEvent)
    if factory_code is not None:
        query = query.join(Terminal, TimeEvent.terminal_id == Terminal.id).where(
            Terminal.factory_code == factory_code
        )
    event = db.scalar(
        query
        .where(_identity_condition(reporter_id, person_id))
        .where(TimeEvent.state_effect.in_([StateEffect.ENTER.value, StateEffect.EXIT.value]))
        .order_by(TimeEvent.event_datetime.desc(), TimeEvent.created_at.desc(), TimeEvent.id.desc())
        .limit(1)
    )
    if event is None or event.state_effect == StateEffect.EXIT.value:
        return WorkerState.OUTSIDE
    return WorkerState.INSIDE
