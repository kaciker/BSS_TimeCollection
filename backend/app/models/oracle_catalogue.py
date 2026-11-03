from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OracleWorkArea(Base):
    __tablename__ = "oracle_work_areas"
    code: Mapped[str] = mapped_column(String(80), primary_key=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)


class OracleMachine(Base):
    __tablename__ = "oracle_machines"
    code: Mapped[str] = mapped_column(String(80), primary_key=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    work_area_code: Mapped[str] = mapped_column(ForeignKey("oracle_work_areas.code", ondelete="RESTRICT"), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)


class OracleCell(Base):
    __tablename__ = "oracle_cells"
    code: Mapped[str] = mapped_column(String(80), primary_key=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    machine_code: Mapped[str] = mapped_column(ForeignKey("oracle_machines.code", ondelete="RESTRICT"), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)


class OraclePayrollTimeType(Base):
    __tablename__ = "oracle_payroll_time_types"
    code: Mapped[str] = mapped_column(String(120), primary_key=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
