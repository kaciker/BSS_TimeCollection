from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class Workshop(Base):
    __tablename__ = "workshops"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    subworkshops = relationship("Subworkshop", back_populates="workshop")

class Subworkshop(Base):
    __tablename__ = "subworkshops"
    __table_args__ = (UniqueConstraint("workshop_id", "code", name="uq_subworkshop_parent_code"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    workshop = relationship("Workshop", back_populates="subworkshops")
    project_lines = relationship("ProjectLine", back_populates="subworkshop")

class ProjectLine(Base):
    __tablename__ = "project_lines"
    __table_args__ = (UniqueConstraint("subworkshop_id", "code", name="uq_project_line_parent_code"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subworkshop_id: Mapped[int] = mapped_column(ForeignKey("subworkshops.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    subworkshop = relationship("Subworkshop", back_populates="project_lines")
