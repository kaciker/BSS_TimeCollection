"""Factory-level presence without personal employee records."""
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class FactoryPerimeterSettings(Base):
    __tablename__ = "factory_perimeter_settings"
    factory_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    badge_source: Mapped[str] = mapped_column(String(16), default="OPEN")
    dedup_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    dedup_seconds: Mapped[int] = mapped_column(Integer, default=5)
    auto_exit_action_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    __table_args__ = (
        CheckConstraint("dedup_seconds >= 0 AND dedup_seconds <= 300", name="ck_perimeter_dedup_seconds"),
        CheckConstraint("badge_source IN ('OPEN', 'EXTERNAL')", name="ck_perimeter_badge_source"),
    )


class FactoryPerimeterEvent(Base):
    __tablename__ = "factory_perimeter_events"
    __table_args__ = (
        CheckConstraint("direction IN ('ENTER', 'EXIT')", name="ck_perimeter_direction"),
        Index("ix_perimeter_presence", "factory_code", "reporter_id", "event_datetime"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    factory_code: Mapped[str] = mapped_column(String(64))
    reporter_id: Mapped[str] = mapped_column(String(160))
    terminal_id: Mapped[int] = mapped_column(ForeignKey("terminals.id"))
    direction: Mapped[str] = mapped_column(String(8))
    event_datetime: Mapped[object] = mapped_column(DateTime(timezone=True))
    correlation_id: Mapped[str] = mapped_column(String(36))
    auto_cell_exit_event_id: Mapped[str | None] = mapped_column(ForeignKey("time_events.id"), nullable=True)
class TerminalBadgeRead(Base):
    __tablename__ = "terminal_badge_reads"
    factory_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    terminal_id: Mapped[int] = mapped_column(ForeignKey("terminals.id"), primary_key=True)
    reporter_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    last_recorded_at: Mapped[object] = mapped_column(DateTime(timezone=True))
