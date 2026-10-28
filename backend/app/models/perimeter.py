"""Factory-level presence with minimized technical identity snapshots."""
from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, event, select
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.person_badge_assignment import PersonBadgeAssignment


class FactoryPerimeterSettings(Base):
    __tablename__ = "factory_perimeter_settings"
    factory_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    badge_source: Mapped[str] = mapped_column(String(16), default="OPEN")
    dedup_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    dedup_seconds: Mapped[int] = mapped_column(Integer, default=5)
    auto_exit_action_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_last_log_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    external_sync_initialized_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_last_sync_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_sync_error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    __table_args__ = (
        CheckConstraint("dedup_seconds >= 0 AND dedup_seconds <= 300", name="ck_perimeter_dedup_seconds"),
        CheckConstraint("badge_source IN ('OPEN', 'EXTERNAL')", name="ck_perimeter_badge_source"),
    )


class FactoryPerimeterEvent(Base):
    __tablename__ = "factory_perimeter_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    factory_code: Mapped[str] = mapped_column(String(64), index=True)
    reporter_id: Mapped[str] = mapped_column(String(160), index=True)
    source_person_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    person_id: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    credential_id: Mapped[str | None] = mapped_column(String(250), nullable=True, index=True)
    terminal_id: Mapped[int] = mapped_column(ForeignKey("terminals.id"))
    direction: Mapped[str] = mapped_column(String(8))
    event_datetime: Mapped[object] = mapped_column(DateTime(timezone=True))
    correlation_id: Mapped[str] = mapped_column(String(36))
    auto_cell_exit_event_id: Mapped[str | None] = mapped_column(ForeignKey("time_events.id"), nullable=True)
    __table_args__ = (CheckConstraint("direction IN ('ENTER', 'EXIT')", name="ck_perimeter_direction"),)


@event.listens_for(FactoryPerimeterEvent, "before_insert")
def snapshot_current_person_badge_identity(mapper, connection, target) -> None:
    """Freeze the locally observed identity for a new perimeter movement when unambiguous."""
    if target.source_person_id and target.person_id and target.credential_id:
        return
    table = PersonBadgeAssignment.__table__
    rows = connection.execute(
        select(
            table.c.source_person_id,
            table.c.person_id,
            table.c.credential_id,
        )
        .where(
            table.c.factory_code == target.factory_code,
            table.c.reader_id == target.reporter_id,
            table.c.observed_to.is_(None),
        )
        .order_by(table.c.observed_from.desc(), table.c.id.desc())
        .limit(2)
    ).all()
    if len(rows) != 1:
        return
    row = rows[0]
    target.source_person_id = target.source_person_id or row.source_person_id
    target.person_id = target.person_id or row.person_id
    target.credential_id = target.credential_id or row.credential_id


class TerminalBadgeRead(Base):
    __tablename__ = "terminal_badge_reads"
    factory_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    terminal_id: Mapped[int] = mapped_column(ForeignKey("terminals.id"), primary_key=True)
    reporter_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    last_recorded_at: Mapped[object] = mapped_column(DateTime(timezone=True))
