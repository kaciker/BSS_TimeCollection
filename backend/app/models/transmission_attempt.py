from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TransmissionAttempt(Base):
    __tablename__ = "transmission_attempts"
    __table_args__ = (Index("ix_transmission_attempts_event", "event_id", "attempt_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("time_events.id", ondelete="CASCADE"))
    attempt_number: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    endpoint: Mapped[str] = mapped_column(String(512))
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[str] = mapped_column(String(32))
    duration_ms: Mapped[int] = mapped_column(Integer)
    request_payload: Mapped[dict] = mapped_column(JSON)
    response_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    event = relationship("TimeEvent", back_populates="attempts")
