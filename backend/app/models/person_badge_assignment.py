from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PersonBadgeAssignment(Base):
    """Observed current PERSON ID to physical credential assignment."""

    __tablename__ = "person_badge_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    factory_code: Mapped[str] = mapped_column(String(64), index=True)
    source_system: Mapped[str] = mapped_column(String(64), default="SQLSERVER_SECURITY_DB")

    source_person_id: Mapped[str] = mapped_column(String(50), index=True)
    person_id: Mapped[str] = mapped_column(String(30), index=True)
    source_card_id: Mapped[str] = mapped_column(String(50))
    credential_id: Mapped[str] = mapped_column(String(250), index=True)

    observed_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    observed_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "ix_person_badge_assignments_factory_person_active",
            "factory_code",
            "source_person_id",
            "observed_to",
        ),
        Index(
            "ix_person_badge_assignments_factory_credential_active",
            "factory_code",
            "credential_id",
            "observed_to",
        ),
    )
