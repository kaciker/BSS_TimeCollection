from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.domain.enums import DeliveryStatus
from app.integrations.oracle.client import OracleClient
from app.models.time_event import TimeEvent
from app.models.transmission_attempt import TransmissionAttempt
from app.schemas.monitoring import (
    AttemptPage, AttemptRead, AttemptSummary, CardPage, CardState,
    EventDetail, EventPage, EventSnapshot,
)

router = APIRouter(prefix="/api/v1/admin/monitoring", tags=["monitoring"])


def _filters(query, terminal_code, reporter_id):
    if terminal_code:
        query = query.where(TimeEvent.terminal_code == terminal_code)
    if reporter_id:
        query = query.where(TimeEvent.reporter_id.contains(reporter_id, autoescape=True))
    return query


def _total(db, query):
    return db.scalar(select(func.count()).select_from(query.subquery())) or 0


@router.get("/events", response_model=EventPage)
def events(
    terminal_code: str | None = None,
    reporter_id: str | None = None,
    delivery_status: DeliveryStatus | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    if start and end and start > end:
        raise HTTPException(422, "The start date must be before the end date")
    query = _filters(select(TimeEvent), terminal_code, reporter_id)
    if delivery_status:
        query = query.where(TimeEvent.delivery_status == delivery_status.value)
    if start:
        query = query.where(TimeEvent.event_datetime >= start)
    if end:
        query = query.where(TimeEvent.event_datetime <= end)
    total = _total(db, query)
    rows = db.scalars(query.order_by(TimeEvent.event_datetime.desc(), TimeEvent.created_at.desc(), TimeEvent.id.desc()).offset(offset).limit(limit)).all()
    return EventPage(items=[EventSnapshot.model_validate(row) for row in rows], total=total)


@router.get("/cards", response_model=CardPage)
def cards(
    terminal_code: str | None = None,
    reporter_id: str | None = None,
    worker_state: Literal["INSIDE", "OUTSIDE"] | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    # Rank globally BEFORE filtering by clock; otherwise a later exit on another
    # terminal would leave a stale INSIDE state on the entry terminal.
    ranked = select(
        TimeEvent.id.label("event_id"),
        func.row_number().over(
            partition_by=TimeEvent.reporter_id,
            order_by=(TimeEvent.event_datetime.desc(), TimeEvent.created_at.desc(), TimeEvent.id.desc()),
        ).label("position"),
    ).where(TimeEvent.state_effect.in_(["ENTER", "EXIT"])).subquery()
    query = select(TimeEvent).join(ranked, ranked.c.event_id == TimeEvent.id).where(ranked.c.position == 1)
    query = _filters(query, terminal_code, reporter_id)
    if worker_state:
        query = query.where(TimeEvent.state_effect == ("ENTER" if worker_state == "INSIDE" else "EXIT"))
    total = _total(db, query)
    rows = db.scalars(query.order_by(TimeEvent.reporter_id).offset(offset).limit(limit)).all()
    return CardPage(items=[CardState(
        reporter_id=row.reporter_id,
        worker_state="INSIDE" if row.state_effect == "ENTER" else "OUTSIDE",
        event=EventSnapshot.model_validate(row),
    ) for row in rows], total=total)


@router.get("/attempts", response_model=AttemptPage)
def attempts(
    terminal_code: str | None = None,
    reporter_id: str | None = None,
    result: DeliveryStatus | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = select(TransmissionAttempt, TimeEvent.reporter_id, TimeEvent.terminal_code).join(TimeEvent, TimeEvent.id == TransmissionAttempt.event_id)
    query = _filters(query, terminal_code, reporter_id)
    if result:
        query = query.where(TransmissionAttempt.result == result.value)
    total = _total(db, query)
    rows = db.execute(query.order_by(TransmissionAttempt.started_at.desc(), TransmissionAttempt.id.desc()).offset(offset).limit(limit)).all()
    return AttemptPage(items=[AttemptSummary(
        **AttemptRead.model_validate(attempt).model_dump(), reporter_id=badge, terminal_code=clock,
    ) for attempt, badge, clock in rows], total=total)


@router.get("/events/{event_id}", response_model=EventDetail)
def event_detail(event_id: str, db: Session = Depends(get_db)):
    event = db.get(TimeEvent, event_id)
    if event is None:
        raise HTTPException(404, "Event not found")
    attempts = db.scalars(select(TransmissionAttempt).where(TransmissionAttempt.event_id == event_id).order_by(TransmissionAttempt.attempt_number, TransmissionAttempt.id)).all()
    preview = OracleClient().build_payload(event)
    # A preview is not an historical send. The actual timestamp/sourceId are
    # available only in the persisted request_payload of each attempt.
    preview.pop("requestTimestamp", None)
    return EventDetail(
        event=EventSnapshot.model_validate(event),
        attempts=[AttemptRead.model_validate(row) for row in attempts],
        oracle_enabled=settings.oracle_enabled,
        oracle_payload_preview=preview,
    )
