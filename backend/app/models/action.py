from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Action(Base):
    __tablename__ = "actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(120))
    supplier_device_event: Mapped[str] = mapped_column(String(128), unique=True)
    state_effect: Mapped[str] = mapped_column(String(16))
    reporter_id_type: Mapped[str] = mapped_column(String(16), default="BADGE")
    oracle_attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    display_order: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    terminals = relationship("Terminal", secondary="terminal_actions", back_populates="actions")
