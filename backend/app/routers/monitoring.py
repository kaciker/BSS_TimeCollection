from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, case, cast, func, literal, or_, select, union_all
from sqlalchemy.orm import Session, aliased

from app.core.config import settings
from app.db.session import get_db
from app.domain.enums import DeliveryStatus
from app.integrations.oracle.client import OracleClient, OracleMappingError
from app.models.person_badge_assignment import PersonBadgeAssignment
from app.models.time_event import TimeEvent
from app.models.perimeter import FactoryPerimeterEvent, FactoryPerimeterSettings, FactoryPresenceProjection
from app.models.terminal import Terminal
from app.models.transmission_attempt import TransmissionAttempt
from app.schemas.monitoring import (
    AttemptPage, AttemptRead, AttemptSummary, CardPage, CardState,
    EventDetail, EventPage, EventSnapshot,
)

router = APIRouter(prefix="/api/v1/admin/monitoring", tags=["monitoring"])


@router.get("/clocks", response_model=list[str])
def clock_codes(db: Session = Depends(get_db)):
    query = union_all(select(TimeEvent.terminal_code), select(Terminal.code).join(FactoryPerimeterEvent, FactoryPerimeterEvent.terminal_id == Terminal.id)).subquery()
    return db.scalars(select(query.c.terminal_code).distinct().order_by(query.c.terminal_code)).all()


def _filters(query, terminal_code, reporter_id):
    if terminal_code:
        query = query.where(TimeEvent.terminal_code == terminal_code)
    if reporter_id:
        query = query.where(or_(
            TimeEvent.reporter_id.contains(reporter_id, autoescape=True),
            TimeEvent.person_id.contains(reporter_id, autoescape=True),
            TimeEvent.credential_id.contains(reporter_id, autoescape=True),
        ))
    return query


def _total(db, query):
    return db.scalar(select(func.count()).select_from(query.subquery())) or 0


def _perimeter_snapshot(db, event):
    terminal = db.get(Terminal, event.terminal_id)
    return EventSnapshot(
        id="perimeter:" + event.id, event_kind="PERIMETER", factory_code=event.factory_code,
        correlation_id=event.correlation_id, auto_cell_exit_event_id=event.auto_cell_exit_event_id,
        terminal_id=event.terminal_id, terminal_code=terminal.code, action_id=None,
        action_code="PERIMETER_" + event.direction, action_label="Factory " + ("entry" if event.direction == "ENTER" else "exit"),
        state_effect=event.direction, reporter_id=event.reporter_id,
        source_person_id=event.source_person_id, person_id=event.person_id, credential_id=event.credential_id,
        event_datetime=event.event_datetime, event_timezone=settings.event_timezone,
        oracle_attributes={}, created_at=event.event_datetime, delivery_status="LOCAL_ONLY",
        attempt_count=0, next_attempt_at=None, last_attempt_at=None, sent_at=None,
        oracle_request_id=None, oracle_event_id=None,
    )


@router.get("/events", response_model=EventPage)
def events(
    terminal_code: str | None = None, reporter_id: str | None = None,
    delivery_status: str | None = None,
    start: datetime | None = None, end: datetime | None = None,
    offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    if start and end and start > end:
        raise HTTPException(422, "The start date must be before the end date")
    if delivery_status and delivery_status not in {s.value for s in DeliveryStatus} | {"LOCAL_ONLY"}:
        raise HTTPException(422, "Invalid delivery status")
    cell = _filters(select(TimeEvent.id.label("id"), TimeEvent.event_datetime.label("at"), TimeEvent.created_at.label("created"), literal("CELL").label("kind")), terminal_code, reporter_id)
    perimeter = select(FactoryPerimeterEvent.id.label("id"), FactoryPerimeterEvent.event_datetime.label("at"), FactoryPerimeterEvent.event_datetime.label("created"), literal("PERIMETER").label("kind")).join(Terminal, Terminal.id == FactoryPerimeterEvent.terminal_id)
    if terminal_code:
        perimeter = perimeter.where(Terminal.code == terminal_code)
    if reporter_id:
        perimeter = perimeter.where(or_(
            FactoryPerimeterEvent.reporter_id.contains(reporter_id, autoescape=True),
            FactoryPerimeterEvent.person_id.contains(reporter_id, autoescape=True),
            FactoryPerimeterEvent.credential_id.contains(reporter_id, autoescape=True),
        ))
    for value, operator in ((start, "ge"), (end, "le")):
        if value:
            cell = cell.where(TimeEvent.event_datetime >= value if operator == "ge" else TimeEvent.event_datetime <= value)
            perimeter = perimeter.where(FactoryPerimeterEvent.event_datetime >= value if operator == "ge" else FactoryPerimeterEvent.event_datetime <= value)
    if delivery_status:
        cell = cell.where(TimeEvent.delivery_status == delivery_status)
        if delivery_status != "LOCAL_ONLY":
            perimeter = perimeter.where(literal(False))
    combined = union_all(cell, perimeter).subquery()
    total = db.scalar(select(func.count()).select_from(combined)) or 0
    rows = db.execute(select(combined).order_by(combined.c.at.desc(), combined.c.created.desc(), combined.c.id.desc()).offset(offset).limit(limit)).all()
    items = [EventSnapshot.model_validate(db.get(TimeEvent, row.id)) if row.kind == "CELL" else _perimeter_snapshot(db, db.get(FactoryPerimeterEvent, row.id)) for row in rows]
    return EventPage(items=items, total=total)


@router.get("/cards", response_model=CardPage)
def cards(
    terminal_code: str | None = None,
    reporter_id: str | None = None,
    worker_state: Literal["INSIDE", "OUTSIDE"] | None = None,
    factory_state: Literal["INSIDE", "OUTSIDE", "UNKNOWN"] | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    # Resolve legacy reporter IDs through observed RFID assignments before ranking.
    # This lets old events and current RFID/perimeter observations share a worker row
    # with new events that already carry person_id.
    identity_ranked = select(
        PersonBadgeAssignment.factory_code.label("factory"),
        PersonBadgeAssignment.reader_id.label("badge"),
        PersonBadgeAssignment.source_person_id.label("source_person_id"),
        PersonBadgeAssignment.person_id.label("person_id"),
        PersonBadgeAssignment.credential_id.label("credential_id"),
        func.row_number().over(
            partition_by=(PersonBadgeAssignment.factory_code, PersonBadgeAssignment.reader_id),
            order_by=(PersonBadgeAssignment.observed_from.desc(), PersonBadgeAssignment.id.desc()),
        ).label("position"),
    ).where(
        PersonBadgeAssignment.observed_to.is_(None),
        PersonBadgeAssignment.reader_id.is_not(None),
    ).subquery()
    cell_identity = identity_ranked.alias("cell_identity")
    cell_events = select(
        TimeEvent.id.label("id"), TimeEvent.reporter_id.label("badge"),
        func.coalesce(TimeEvent.person_id, cell_identity.c.person_id).label("person_id"),
        func.coalesce(TimeEvent.source_person_id, cell_identity.c.source_person_id).label("source_person_id"),
        func.coalesce(TimeEvent.credential_id, cell_identity.c.credential_id).label("credential_id"),
        TimeEvent.terminal_code.label("clock"), TimeEvent.state_effect.label("effect"),
        TimeEvent.event_datetime.label("at"), TimeEvent.created_at.label("created"),
        literal("CELL").label("kind"), literal(0).label("final_movement"),
        func.coalesce(Terminal.factory_code, "DEFAULT").label("factory"),
    ).outerjoin(Terminal, Terminal.id == TimeEvent.terminal_id).outerjoin(
        cell_identity,
        (cell_identity.c.factory == func.coalesce(Terminal.factory_code, "DEFAULT"))
        & (cell_identity.c.badge == TimeEvent.reporter_id)
        & (cell_identity.c.position == 1),
    ).where(TimeEvent.state_effect.in_(["ENTER", "EXIT"]))
    perimeter_identity = identity_ranked.alias("perimeter_identity")
    perimeter_events = select(
        FactoryPerimeterEvent.id.label("id"), FactoryPerimeterEvent.reporter_id.label("badge"),
        func.coalesce(FactoryPerimeterEvent.person_id, perimeter_identity.c.person_id).label("person_id"),
        func.coalesce(FactoryPerimeterEvent.source_person_id, perimeter_identity.c.source_person_id).label("source_person_id"),
        func.coalesce(FactoryPerimeterEvent.credential_id, perimeter_identity.c.credential_id).label("credential_id"),
        Terminal.code.label("clock"), FactoryPerimeterEvent.direction.label("effect"),
        FactoryPerimeterEvent.event_datetime.label("at"), FactoryPerimeterEvent.event_datetime.label("created"),
        literal("PERIMETER").label("kind"), literal(1).label("final_movement"),
        FactoryPerimeterEvent.factory_code.label("factory"),
    ).join(Terminal, Terminal.id == FactoryPerimeterEvent.terminal_id).outerjoin(
        perimeter_identity,
        (perimeter_identity.c.factory == FactoryPerimeterEvent.factory_code)
        & (perimeter_identity.c.badge == FactoryPerimeterEvent.reporter_id)
        & (perimeter_identity.c.position == 1),
    )
    combined = union_all(cell_events, perimeter_events).subquery()
    ranked = select(
        combined,
        func.coalesce(combined.c.person_id, combined.c.badge).label("identity_key"),
        func.row_number().over(
            partition_by=func.coalesce(combined.c.person_id, combined.c.badge),
            order_by=(combined.c.at.desc(), combined.c.final_movement.desc(), combined.c.created.desc(), combined.c.id.desc()),
        ).label("position"),
    ).subquery()
    cell_rows = cell_events.subquery("cell_rows")
    perimeter_rows = perimeter_events.subquery("perimeter_rows")
    cell_ranked = select(
        cell_rows.c.factory.label("factory"),
        func.coalesce(cell_rows.c.person_id, cell_rows.c.badge).label("identity_key"),
        cell_rows.c.effect.label("effect"),
        func.row_number().over(
            partition_by=(cell_rows.c.factory, func.coalesce(cell_rows.c.person_id, cell_rows.c.badge)),
            order_by=(cell_rows.c.at.desc(), cell_rows.c.created.desc(), cell_rows.c.id.desc()),
        ).label("position"),
    ).subquery()
    perimeter_ranked = select(
        perimeter_rows.c.factory.label("factory"),
        func.coalesce(perimeter_rows.c.person_id, perimeter_rows.c.badge).label("identity_key"),
        perimeter_rows.c.effect.label("effect"),
        func.row_number().over(
            partition_by=(perimeter_rows.c.factory, func.coalesce(perimeter_rows.c.person_id, perimeter_rows.c.badge)),
            order_by=(perimeter_rows.c.at.desc(), perimeter_rows.c.id.desc()),
        ).label("position"),
    ).subquery()
    cell_state = case((cell_ranked.c.effect == "ENTER", "INSIDE"), else_="OUTSIDE")
    projection_key = case(
        (ranked.c.person_id.is_not(None), literal("PERSON:").concat(cast(ranked.c.person_id, String))),
        (ranked.c.badge.is_not(None), literal("READER:").concat(cast(ranked.c.badge, String))),
        else_=literal(""),
    )
    # Legacy badges without canonical person_id resolve through their observed
    # Reader ID projection. A canonical person's UNKNOWN projection remains
    # authoritative and is not overridden by a reader-level row.
    reader_projection = aliased(FactoryPresenceProjection)
    use_reader_projection = ranked.c.person_id.is_(None)
    factory_state_value = case((use_reader_projection, reader_projection.state), else_=FactoryPresenceProjection.state)
    factory_verified_value = case((use_reader_projection, reader_projection.verified_at), else_=FactoryPresenceProjection.verified_at)
    factory_movement_value = case((use_reader_projection, reader_projection.source_movement_at), else_=FactoryPresenceProjection.source_movement_at)
    factory_resolution_value = case((use_reader_projection, reader_projection.resolution_code), else_=FactoryPresenceProjection.resolution_code)
    factory_reason_value = func.coalesce(
        case((use_reader_projection, reader_projection.unresolved_reason), else_=FactoryPresenceProjection.unresolved_reason),
        "NO_PROJECTION",
    )
    query = select(
        ranked,
        ranked.c.badge.label("state_identity_key"),
        cell_state.label("cell_state"),
        case(
            (FactoryPerimeterSettings.enabled.is_(True), func.coalesce(factory_state_value, "UNKNOWN")),
            else_=None,
        ).label("factory_state"),
        factory_verified_value.label("factory_verified_at"),
        factory_movement_value.label("factory_movement_at"),
        factory_resolution_value.label("factory_resolution"),
        factory_reason_value.label("factory_reason"),
    ).select_from(ranked).outerjoin(
        cell_ranked,
        (cell_ranked.c.factory == ranked.c.factory)
        & (cell_ranked.c.identity_key == ranked.c.identity_key)
        & (cell_ranked.c.position == 1),
    ).outerjoin(
        perimeter_ranked,
        (perimeter_ranked.c.factory == ranked.c.factory)
        & (perimeter_ranked.c.identity_key == ranked.c.identity_key)
        & (perimeter_ranked.c.position == 1),
    ).outerjoin(FactoryPerimeterSettings, FactoryPerimeterSettings.factory_code == ranked.c.factory
    ).outerjoin(
        FactoryPresenceProjection,
        (FactoryPresenceProjection.factory_code == ranked.c.factory)
        & (FactoryPresenceProjection.tracking_key == projection_key),
    ).outerjoin(
        reader_projection,
        use_reader_projection
        & (reader_projection.factory_code == ranked.c.factory)
        & (reader_projection.tracking_key == literal("READER:").concat(cast(ranked.c.badge, String))),
    ).where(ranked.c.position == 1)
    if terminal_code:
        query = query.where(ranked.c.clock == terminal_code)
    if reporter_id:
        query = query.where(or_(
            ranked.c.badge.contains(reporter_id, autoescape=True),
            ranked.c.person_id.contains(reporter_id, autoescape=True),
            ranked.c.credential_id.contains(reporter_id, autoescape=True),
            ranked.c.source_person_id.contains(reporter_id, autoescape=True),
        ))
    if worker_state:
        query = query.where(cell_state == worker_state)
    if factory_state:
        query = query.where(
            FactoryPerimeterSettings.enabled.is_(True),
            func.coalesce(factory_state_value, "UNKNOWN") == factory_state,
        )
    total = _total(db, query)
    rows = db.execute(query.order_by(ranked.c.badge, ranked.c.at.desc(), ranked.c.factory).offset(offset).limit(limit)).all()
    enabled = bool(db.scalar(select(func.count()).select_from(FactoryPerimeterSettings).where(FactoryPerimeterSettings.enabled.is_(True))))
    items = []
    for row in rows:
        event = EventSnapshot.model_validate(db.get(TimeEvent, row.id)) if row.kind == "CELL" else _perimeter_snapshot(db, db.get(FactoryPerimeterEvent, row.id))
        items.append(CardState(
            reporter_id=row.state_identity_key,
            source_person_id=row.source_person_id or event.source_person_id,
            person_id=row.person_id or event.person_id,
            credential_id=row.credential_id or event.credential_id,
            worker_state=row.cell_state,
            factory_code=row.factory,
            factory_state=row.factory_state,
            factory_verified_at=row.factory_verified_at,
            factory_movement_at=row.factory_movement_at,
            factory_resolution=row.factory_resolution,
            factory_reason=row.factory_reason if row.factory_state == "UNKNOWN" else None,
            event=event,
        ))
    return CardPage(items=items, total=total, factory_perimeter_enabled=enabled)

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
    if event_id.startswith("perimeter:"):
        movement = db.get(FactoryPerimeterEvent, event_id.removeprefix("perimeter:"))
        if movement is None:
            raise HTTPException(404, "Event not found")
        return EventDetail(event=_perimeter_snapshot(db, movement), attempts=[], oracle_enabled=settings.oracle_enabled, oracle_payload_preview=None)
    event = db.get(TimeEvent, event_id)
    if event is None:
        raise HTTPException(404, "Event not found")
    attempts = db.scalars(select(TransmissionAttempt).where(TransmissionAttempt.event_id == event_id).order_by(TransmissionAttempt.attempt_number, TransmissionAttempt.id)).all()
    try:
        preview = OracleClient().build_payload(event)
    except OracleMappingError:
        preview = None
        db.flush()
    # A preview is not an historical send. The actual timestamp/sourceId are
    # available only in the persisted request_payload of each attempt.
    if preview is not None:
        preview.pop("requestTimestamp", None)
    return EventDetail(
        event=EventSnapshot.model_validate(event),
        attempts=[AttemptRead.model_validate(row) for row in attempts],
        oracle_enabled=settings.oracle_enabled,
        oracle_payload_preview=preview,
        oracle_mapping_error=event.oracle_mapping_error,
    )
