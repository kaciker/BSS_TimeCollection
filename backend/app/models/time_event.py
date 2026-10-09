from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TimeEvent(Base):
    __tablename__ = "time_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_number: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    terminal_id: Mapped[int] = mapped_column(ForeignKey("terminals.id"))
    action_id: Mapped[int] = mapped_column(ForeignKey("actions.id"))

    terminal_code: Mapped[str] = mapped_column(String(64))
    device_id: Mapped[str] = mapped_column(String(128))
    action_code: Mapped[str] = mapped_column(String(64))
    action_label: Mapped[str] = mapped_column(String(120))
    supplier_device_event: Mapped[str] = mapped_column(String(128))
    state_effect: Mapped[str] = mapped_column(String(16))

    reporter_id: Mapped[str] = mapped_column(String(160), index=True)
    reporter_id_type: Mapped[str] = mapped_column(String(16))
    identification_method: Mapped[str] = mapped_column(String(16))

    event_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    event_timezone: Mapped[str] = mapped_column(String(64))
    oracle_attributes: Mapped[dict] = mapped_column(JSON, default=dict)

    delivery_status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    oracle_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    oracle_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    terminal = relationship("Terminal")
    action = relationship("Action")
    attempts = relationship("TransmissionAttempt", back_populates="event", cascade="all, delete-orphan")
