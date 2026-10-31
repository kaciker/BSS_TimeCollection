"""Factory-level presence with minimized technical identity snapshots."""
from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, event, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.base import Base
from app.models.person_badge_assignment import PersonBadgeAssignment


class FactoryPerimeterSettings(Base):
    __tablename__ = "factory_perimeter_settings"
    factory_code: Mapped[str] = mapped_column(String(64), ForeignKey("factories.code", ondelete="RESTRICT"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    badge_source: Mapped[str] = mapped_column(String(16), default="OPEN")
    dedup_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    dedup_seconds: Mapped[int] = mapped_column(Integer, default=5)
    auto_exit_action_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_last_log_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    external_sync_window_from: Mapped[object | None] = mapped_column(DateTime(timezone=False), nullable=True)
    external_sync_cursor_created_at: Mapped[object | None] = mapped_column(DateTime(timezone=False), nullable=True)
    external_sync_cursor_transaction_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
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
    factory_code: Mapped[str] = mapped_column(String(64), ForeignKey("factories.code", ondelete="RESTRICT"), index=True)
    reporter_id: Mapped[str] = mapped_column(String(160), index=True)
    source_person_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    person_id: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    credential_id: Mapped[str | None] = mapped_column(String(250), nullable=True, index=True)
    terminal_id: Mapped[int] = mapped_column(ForeignKey("terminals.id"))
    direction: Mapped[str] = mapped_column(String(8))
    event_datetime: Mapped[object] = mapped_column(DateTime(timezone=True))
    correlation_id: Mapped[str] = mapped_column(String(36))
    source_system: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_transaction_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_log_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_unique_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auto_cell_exit_event_id: Mapped[str | None] = mapped_column(ForeignKey("time_events.id"), nullable=True)
    __table_args__ = (
        CheckConstraint("direction IN ('ENTER', 'EXIT')", name="ck_perimeter_direction"),
        Index(
            "ix_factory_perimeter_events_source_transaction",
            "factory_code", "source_system", "source_transaction_id",
            unique=True,
            postgresql_where=source_transaction_id.is_not(None),
        ),
    )


@event.listens_for(Session, "before_flush")
def snapshot_current_person_badge_identity(session, flush_context, instances) -> None:
    """Freeze the active local identity before new perimeter rows are inserted."""
    for target in tuple(session.new):
        if not isinstance(target, FactoryPerimeterEvent):
            continue
        if target.source_person_id and target.person_id and target.credential_id:
            continue

        rows = session.execute(
            select(
                PersonBadgeAssignment.source_person_id,
                PersonBadgeAssignment.person_id,
                PersonBadgeAssignment.credential_id,
            )
            .where(
                PersonBadgeAssignment.factory_code == target.factory_code,
                PersonBadgeAssignment.reader_id == target.reporter_id,
                PersonBadgeAssignment.observed_to.is_(None),
            )
            .order_by(PersonBadgeAssignment.observed_from.desc(), PersonBadgeAssignment.id.desc())
            .limit(2)
        ).all()
        if len(rows) != 1:
            continue

        row = rows[0]
        target.source_person_id = target.source_person_id or row.source_person_id
        target.person_id = target.person_id or row.person_id
        target.credential_id = target.credential_id or row.credential_id


class TerminalBadgeRead(Base):
    __tablename__ = "terminal_badge_reads"
    factory_code: Mapped[str] = mapped_column(String(64), ForeignKey("factories.code", ondelete="RESTRICT"), primary_key=True)
    terminal_id: Mapped[int] = mapped_column(ForeignKey("terminals.id"), primary_key=True)
    reporter_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    last_recorded_at: Mapped[object] = mapped_column(DateTime(timezone=True))
