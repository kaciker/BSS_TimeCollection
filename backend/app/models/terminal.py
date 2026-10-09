from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

terminal_actions = Table(
    "terminal_actions",
    Base.metadata,
    Column("terminal_id", ForeignKey("terminals.id", ondelete="CASCADE"), primary_key=True),
    Column("action_id", ForeignKey("actions.id", ondelete="CASCADE"), primary_key=True),
)


class Terminal(Base):
    __tablename__ = "terminals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    external_device_id: Mapped[str] = mapped_column(String(128), unique=True)
    identification_mode: Mapped[str] = mapped_column(String(16), default="BOTH")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    actions = relationship("Action", secondary=terminal_actions, back_populates="terminals")
