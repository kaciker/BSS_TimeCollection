from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Action(Base):
    __tablename__ = "actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(120))
    # Local BSS supplier code is retained for audit. Oracle supplier events are
    # a separate directional contract field and may be shared by many actions.
    supplier_device_event: Mapped[str] = mapped_column(String(128))
    oracle_supplier_event: Mapped[str] = mapped_column(String(40))
    state_effect: Mapped[str] = mapped_column(String(16))
    oracle_payroll_time_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    oracle_attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    visual_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=100)
    requires_subaction: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_action_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("actions.id", ondelete="SET NULL"), nullable=True, index=True)
    show_on_terminal: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    terminals = relationship("Terminal", secondary="terminal_actions", back_populates="actions")
    parent_action = relationship("Action", remote_side=[id], back_populates="subactions")
    subactions = relationship("Action", back_populates="parent_action")


@event.listens_for(Action, "before_insert")
def _default_oracle_supplier_event(_mapper, _connection, action: Action) -> None:
    """Default the POC Oracle event while preserving each local BSS event code."""
    if not action.oracle_supplier_event:
        action.oracle_supplier_event = (
            "HUT_TCD_SUPP1_IN_2" if action.state_effect == "ENTER" else "HUT_TCD_SUPP1_OUT_2"
        )
