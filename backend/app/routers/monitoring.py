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
from app.services.rfid_identity import rfid_equivalence_key, rfid_equivalence_key_sql
from app.services.oracle_readiness import oracle_readiness_errors, is_oracle_ready

router = APIRouter(prefix="/api/v1/admin/monitoring", tags=["monitoring"])


def _reader_key(expression, db):
    return rfid_equivalence_key_sql(expression, dialect=db.get_bind().dialect.name)


def _active_identity_map(db):
    # Collapse exact, zero-padded/unpadded RAW, and byte-swapped spellings to
    # one lookup key. Ambiguous keys are excluded by the counts below.
    key = _reader_key(PersonBadgeAssignment.reader_id, db)
    grouped = select(
        PersonBadgeAssignment.factory_code.label("factory"), key.label("reader_key"),
        func.count(func.distinct(PersonBadgeAssignment.person_id)).label("people"),
        func.count(func.distinct(PersonBadgeAssignment.source_person_id)).label("source_people"),
        func.count(func.distinct(PersonBadgeAssignment.credential_id)).label("credentials"),
        func.count(func.distinct(PersonBadgeAssignment.source_card_id)).label("cards"),
        func.min(PersonBadgeAssignment.person_id).label("person_id"),
        func.min(PersonBadgeAssignment.source_person_id).label("source_person_id"),
        func.min(PersonBadgeAssignment.credential_id).label("credential_id"),
    ).where(
        PersonBadgeAssignment.observed_to.is_(None),
        PersonBadgeAssignment.reader_id.is_not(None), key.is_not(None),
    ).group_by(PersonBadgeAssignment.factory_code, key).subquery()
    return select(
        grouped.c.factory, grouped.c.reader_key,
        case(((grouped.c.people == 1) & (grouped.c.source_people == 1)
              & (grouped.c.credentials == 1) & (grouped.c.cards == 1), grouped.c.person_id)).label("person_id"),
        case(((grouped.c.people == 1) & (grouped.c.source_people == 1)
              & (grouped.c.credentials == 1) & (grouped.c.cards == 1), grouped.c.source_person_id)).label("source_person_id"),
        case(((grouped.c.people == 1) & (grouped.c.source_people == 1)
              & (grouped.c.credentials == 1) & (grouped.c.cards == 1), grouped.c.credential_id)).label("credential_id"),
    ).where((grouped.c.people == 1) & (grouped.c.source_people == 1)
            & (grouped.c.credentials == 1) & (grouped.c.cards == 1)).subquery("active_identity_map")


def _enrich_events(db, snapshots):
    """Enrich historical snapshots only when an active RFID map is unambiguous."""
    if not snapshots:
        return snapshots
    rows = db.scalars(select(PersonBadgeAssignment).where(
        PersonBadgeAssignment.observed_to.is_(None),
        PersonBadgeAssignment.reader_id.is_not(None),
    )).all()
    grouped = {}
    for row in rows:
        try:
            key = (row.factory_code, rfid_equivalence_key(row.reader_id))
        except ValueError:
            continue
        grouped.setdefault(key, set()).add((row.person_id, row.source_person_id,
                                             row.credential_id, row.source_card_id))
    for snapshot in snapshots:
        factory = snapshot.factory_code
        if factory is None:
            terminal = db.get(Terminal, snapshot.terminal_id)
            factory = terminal.factory_code if terminal and terminal.factory_code else "DEFAULT"
        try:
            identities = grouped.get((factory, rfid_equivalence_key(snapshot.reporter_id)), set())
        except ValueError:
            continue
        if len(identities) != 1:
            continue
        person_id, source_person_id, credential_id, _card = next(iter(identities))
        snapshot.person_id = snapshot.person_id or person_id
        snapshot.source_person_id = snapshot.source_person_id or source_person_id
        snapshot.credential_id = snapshot.credential_id or credential_id
    return snapshots


def _reader_keys_for_person_search(db, search: str) -> set[str]:
    rows = db.scalars(select(PersonBadgeAssignment).where(
        PersonBadgeAssignment.observed_to.is_(None),
        or_(PersonBadgeAssignment.person_id == search,
            PersonBadgeAssignment.source_person_id == search,
            PersonBadgeAssignment.credential_id == search),
    )).all()
    requested = set()
    for row in rows:
        if row.reader_id:
            try:
                requested.add((row.factory_code, rfid_equivalence_key(row.reader_id)))
            except ValueError:
                continue
    if not requested:
        return set()
    active = db.scalars(select(PersonBadgeAssignment).where(
        PersonBadgeAssignment.observed_to.is_(None),
        PersonBadgeAssignment.reader_id.is_not(None),
    )).all()
    identities = {}
    for row in active:
        try:
            key = (row.factory_code, rfid_equivalence_key(row.reader_id))
        except ValueError:
            continue
        identities.setdefault(key, set()).add((row.person_id, row.source_person_id,
                                                 row.credential_id, row.source_card_id))
    return {key for key in requested if len(identities.get(key, ())) == 1}



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
        source_event_datetime=event.source_event_datetime,
        effective_event_datetime=event.effective_event_datetime or event.event_datetime,
        source_clock_offset_minutes=event.source_clock_offset_minutes,
        terminal_id=event.terminal_id, terminal_code=terminal.code, action_id=None,
        action_code="PERIMETER_" + event.direction, action_label="Factory " + ("entry" if event.direction == "ENTER" else "exit"),
        state_effect=event.direction, reporter_id=event.reporter_id,
        source_person_id=event.source_person_id, person_id=event.person_id, credential_id=event.credential_id,
        event_datetime=event.effective_event_datetime or event.event_datetime, event_timezone=settings.event_timezone,
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
    search_keys = _reader_keys_for_person_search(db, reporter_id) if reporter_id else set()
    cell = select(TimeEvent.id.label("id"), TimeEvent.event_datetime.label("at"), TimeEvent.created_at.label("created"), literal("CELL").label("kind"))
    if reporter_id:
        cell = cell.outerjoin(Terminal, Terminal.id == TimeEvent.terminal_id).where(or_(
            TimeEvent.reporter_id.contains(reporter_id, autoescape=True),
            TimeEvent.person_id.contains(reporter_id, autoescape=True),
            TimeEvent.credential_id.contains(reporter_id, autoescape=True),
            TimeEvent.source_person_id.contains(reporter_id, autoescape=True),
            *[(_reader_key(TimeEvent.reporter_id, db) == literal(key)) &
              (func.coalesce(Terminal.factory_code, "DEFAULT") == factory)
              for factory, key in search_keys],
        ))
    if terminal_code:
        cell = cell.where(TimeEvent.terminal_code == terminal_code)
    perimeter = select(FactoryPerimeterEvent.id.label("id"), func.coalesce(FactoryPerimeterEvent.effective_event_datetime, FactoryPerimeterEvent.event_datetime).label("at"), FactoryPerimeterEvent.event_datetime.label("created"), literal("PERIMETER").label("kind")).join(Terminal, Terminal.id == FactoryPerimeterEvent.terminal_id)
    if terminal_code:
        perimeter = perimeter.where(Terminal.code == terminal_code)
    if reporter_id:
        perimeter = perimeter.where(or_(
            FactoryPerimeterEvent.reporter_id.contains(reporter_id, autoescape=True),
            FactoryPerimeterEvent.person_id.contains(reporter_id, autoescape=True),
            FactoryPerimeterEvent.credential_id.contains(reporter_id, autoescape=True),
            FactoryPerimeterEvent.source_person_id.contains(reporter_id, autoescape=True),
            *[(_reader_key(FactoryPerimeterEvent.reporter_id, db) == literal(key)) &
              (FactoryPerimeterEvent.factory_code == factory)
              for factory, key in search_keys],
        ))
    for value, operator in ((start, "ge"), (end, "le")):
        if value:
            cell = cell.where(TimeEvent.event_datetime >= value if operator == "ge" else TimeEvent.event_datetime <= value)
            perimeter = perimeter.where(func.coalesce(FactoryPerimeterEvent.effective_event_datetime, FactoryPerimeterEvent.event_datetime) >= value if operator == "ge" else func.coalesce(FactoryPerimeterEvent.effective_event_datetime, FactoryPerimeterEvent.event_datetime) <= value)
    if delivery_status:
        cell = cell.where(TimeEvent.delivery_status == delivery_status)
        if delivery_status != "LOCAL_ONLY":
            perimeter = perimeter.where(literal(False))
    combined = union_all(cell, perimeter).subquery()
    total = db.scalar(select(func.count()).select_from(combined)) or 0
    rows = db.execute(select(combined).order_by(combined.c.at.desc(), combined.c.created.desc(), combined.c.id.desc()).offset(offset).limit(limit)).all()
    items = [EventSnapshot.model_validate(db.get(TimeEvent, row.id)) if row.kind == "CELL" else _perimeter_snapshot(db, db.get(FactoryPerimeterEvent, row.id)) for row in rows]
    _enrich_events(db, items)
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
    identity_map = _active_identity_map(db)
    cell_identity = identity_map.alias("cell_identity")
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
        &
        (_reader_key(cell_identity.c.reader_key, db) == _reader_key(TimeEvent.reporter_id, db)),
    ).where(TimeEvent.state_effect.in_(["ENTER", "EXIT"]))
    perimeter_identity = identity_map.alias("perimeter_identity")
    perimeter_events = select(
        FactoryPerimeterEvent.id.label("id"), FactoryPerimeterEvent.reporter_id.label("badge"),
        func.coalesce(FactoryPerimeterEvent.person_id, perimeter_identity.c.person_id).label("person_id"),
        func.coalesce(FactoryPerimeterEvent.source_person_id, perimeter_identity.c.source_person_id).label("source_person_id"),
        func.coalesce(FactoryPerimeterEvent.credential_id, perimeter_identity.c.credential_id).label("credential_id"),
        Terminal.code.label("clock"), FactoryPerimeterEvent.direction.label("effect"),
        func.coalesce(FactoryPerimeterEvent.effective_event_datetime, FactoryPerimeterEvent.event_datetime).label("at"), FactoryPerimeterEvent.event_datetime.label("created"),
        literal("PERIMETER").label("kind"), literal(1).label("final_movement"),
        FactoryPerimeterEvent.factory_code.label("factory"),
    ).join(Terminal, Terminal.id == FactoryPerimeterEvent.terminal_id).outerjoin(
        perimeter_identity,
        (perimeter_identity.c.factory == FactoryPerimeterEvent.factory_code)
        &
        (_reader_key(perimeter_identity.c.reader_key, db) == _reader_key(FactoryPerimeterEvent.reporter_id, db)),
    )
    combined = union_all(cell_events, perimeter_events).subquery()
    resolved_badge = func.coalesce(combined.c.person_id, combined.c.badge)
    ranked = select(
        combined, resolved_badge.label("identity_key"),
        func.row_number().over(
            partition_by=resolved_badge,
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
            partition_by=func.coalesce(cell_rows.c.person_id, cell_rows.c.badge),
            order_by=(cell_rows.c.at.desc(), cell_rows.c.created.desc(), cell_rows.c.id.desc()),
        ).label("position"),
    ).subquery()
    perimeter_ranked = select(
        perimeter_rows.c.factory.label("factory"),
        func.coalesce(perimeter_rows.c.person_id, perimeter_rows.c.badge).label("identity_key"),
        perimeter_rows.c.effect.label("effect"),
        func.row_number().over(
            partition_by=func.coalesce(perimeter_rows.c.person_id, perimeter_rows.c.badge),
            order_by=(perimeter_rows.c.at.desc(), perimeter_rows.c.id.desc()),
        ).label("position"),
    ).subquery()
    cell_state = case((cell_ranked.c.effect == "ENTER", "INSIDE"), else_="OUTSIDE")
    # Legacy badges without canonical person_id resolve through their observed
    # Reader ID projection. A canonical person's UNKNOWN projection remains
    # authoritative and is not overridden by a reader-level row.
    reader_projection = aliased(FactoryPresenceProjection)
    canonical_projection = aliased(FactoryPresenceProjection)
    use_reader_projection = ranked.c.person_id.is_(None)
    factory_state_value = case((use_reader_projection, reader_projection.state), else_=canonical_projection.state)
    factory_projection_exists = case(
        (use_reader_projection, reader_projection.id.is_not(None)),
        else_=canonical_projection.id.is_not(None),
    )
    factory_verified_value = case((use_reader_projection, reader_projection.verified_at), else_=canonical_projection.verified_at)
    factory_movement_value = case((use_reader_projection, reader_projection.source_movement_at), else_=canonical_projection.source_movement_at)
    factory_resolution_value = case((use_reader_projection, reader_projection.resolution_code), else_=canonical_projection.resolution_code)
    factory_reason_value = func.coalesce(
        case((use_reader_projection, reader_projection.unresolved_reason), else_=canonical_projection.unresolved_reason),
        "NO_PROJECTION",
    )
    factory_enabled = aliased(FactoryPerimeterSettings)
    query = select(
        ranked,
        ranked.c.badge.label("state_identity_key"),
        cell_state.label("cell_state"),
        case(
            (factory_enabled.enabled.is_(True), func.coalesce(factory_state_value, "UNKNOWN")),
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
    ).outerjoin(factory_enabled, factory_enabled.factory_code == ranked.c.factory
    ).outerjoin(
        reader_projection,
        use_reader_projection
        & (reader_projection.factory_code == ranked.c.factory)
        & (reader_projection.tracking_key == literal("READER:").concat(cast(ranked.c.badge, String))),
    ).outerjoin(
        canonical_projection,
        (canonical_projection.factory_code == ranked.c.factory)
        & (canonical_projection.tracking_key == literal("PERSON:").concat(cast(ranked.c.person_id, String))),
    ).where(ranked.c.position == 1)
    if terminal_code:
        query = query.where(ranked.c.clock == terminal_code)
    if reporter_id:
        query = query.where(or_(
            ranked.c.badge.contains(reporter_id, autoescape=True),
            ranked.c.person_id.contains(reporter_id, autoescape=True),
            ranked.c.credential_id.contains(reporter_id, autoescape=True),
            ranked.c.source_person_id.contains(reporter_id, autoescape=True),
            ranked.c.identity_key == reporter_id,
            _reader_key(ranked.c.badge, db) == _reader_key(literal(reporter_id), db),
        ))
    if worker_state:
        query = query.where(cell_state == worker_state)
    if factory_state:
        projection_matches = case(
            (ranked.c.person_id.is_(None), reader_projection.state == factory_state),
            else_=canonical_projection.state == factory_state,
        )
        query = query.where(
            factory_enabled.enabled.is_(True),
            factory_projection_exists,
            projection_matches,
        )
    total = _total(db, query)
    rows = db.execute(query.order_by(ranked.c.badge, ranked.c.at.desc(), ranked.c.factory).offset(offset).limit(limit)).all()
    enabled = bool(db.scalar(select(func.count()).select_from(FactoryPerimeterSettings).where(FactoryPerimeterSettings.enabled.is_(True))))
    items = []
    for row in rows:
        event = EventSnapshot.model_validate(db.get(TimeEvent, row.id)) if row.kind == "CELL" else _perimeter_snapshot(db, db.get(FactoryPerimeterEvent, row.id))
        _enrich_events(db, [event])
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
        preview = OracleClient().build_payload(event, db=db)
    except OracleMappingError:
        preview = None
    mapping_error = "; ".join(oracle_readiness_errors(event, db))[:255] or None
    # A preview is not an historical send. The actual timestamp/sourceId are
    # available only in the persisted request_payload of each attempt.
    if preview is not None:
        preview.pop("requestTimestamp", None)
    snapshot = EventSnapshot.model_validate(event)
    snapshot = snapshot.model_copy(update={
        "oracle_ready": is_oracle_ready(event, db),
        "oracle_mapping_error": mapping_error,
    })
    return EventDetail(
        event=snapshot,
        attempts=[AttemptRead.model_validate(row) for row in attempts],
        oracle_enabled=settings.oracle_enabled,
        oracle_payload_preview=preview,
        oracle_mapping_error=mapping_error,
    )
