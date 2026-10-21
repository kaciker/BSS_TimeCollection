from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WorkerRuntimeMetrics(Base):
    """Bounded singleton telemetry row; contains no event or worker identifiers."""
    __tablename__ = "worker_runtime_metrics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    process_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                        default=lambda: datetime.now(timezone.utc))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_cycle_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (CheckConstraint("id = 1", name="ck_worker_runtime_metrics_singleton"),)
