from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, JSON, String, Table
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
    __table_args__ = (CheckConstraint("terminal_role IN ('CELL', 'PERIMETER_ENTER', 'PERIMETER_EXIT', 'PERIMETER_BOTH')", name="ck_terminal_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    factory_code: Mapped[str] = mapped_column(String(64), default='DEFAULT')
    terminal_role: Mapped[str] = mapped_column(String(16), default='CELL')
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    external_device_id: Mapped[str] = mapped_column(String(128), unique=True)
    identification_mode: Mapped[str] = mapped_column(String(16), default="BOTH")
    reporter_id_type: Mapped[str] = mapped_column(String(16), default="BADGE")
    oracle_attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    project_line_id: Mapped[int | None] = mapped_column(ForeignKey("project_lines.id", ondelete="RESTRICT"), nullable=True, index=True)
    project_line = relationship("ProjectLine")
    activation_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    session_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    actions = relationship("Action", secondary=terminal_actions, back_populates="terminals")
