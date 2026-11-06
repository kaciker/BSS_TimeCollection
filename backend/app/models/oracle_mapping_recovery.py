from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class OracleMappingRecoveryAudit(Base):
    __tablename__ = "oracle_mapping_recovery_audit"
    __table_args__ = (UniqueConstraint("event_id", "field_name", name="uq_oracle_mapping_recovery_event_field"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("time_events.id", ondelete="RESTRICT"), index=True)
    field_name: Mapped[str] = mapped_column(String(80), nullable=False)
    previous_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str] = mapped_column(Text, nullable=False)
    source_action_id: Mapped[int] = mapped_column(ForeignKey("actions.id", ondelete="RESTRICT"), nullable=False)
    source_action_code: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    recovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    recovery_reason: Mapped[str] = mapped_column(Text, nullable=False)

    event = relationship("TimeEvent", back_populates="mapping_recoveries")
