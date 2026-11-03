"""Database-backed Oracle catalogue queries and import validation."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.oracle_catalogue import OracleCell, OracleMachine, OraclePayrollTimeType, OracleWorkArea


def catalogue_payload(db: Session, *, include_inactive: bool = False) -> dict:
    active_filter = () if include_inactive else (OracleWorkArea.active.is_(True),)
    work_areas = db.scalars(select(OracleWorkArea).where(*active_filter).order_by(OracleWorkArea.code)).all()
    machines = db.scalars(select(OracleMachine).where(*(() if include_inactive else (OracleMachine.active.is_(True),))).order_by(OracleMachine.code)).all()
    cells = db.scalars(select(OracleCell).where(*(() if include_inactive else (OracleCell.active.is_(True),))).order_by(OracleCell.code)).all()
    payroll = db.scalars(select(OraclePayrollTimeType).where(*(() if include_inactive else (OraclePayrollTimeType.active.is_(True),))).order_by(OraclePayrollTimeType.code)).all()
    return {
        "payroll_time_types": ([{"code": row.code, "description": row.description, "active": row.active} for row in payroll] if include_inactive else [row.code for row in payroll]),
        "work_areas": [{"code": row.code, "description": row.description, "active": row.active} for row in work_areas],
        "machines": [{"code": row.code, "description": row.description, "work_area": row.work_area_code, "active": row.active} for row in machines],
        "cells": [{"code": row.code, "description": row.description, "machine": row.machine_code, "active": row.active} for row in cells],
    }


def structure_parent_mapping_errors(db: Session, *, work_area: str | None, machine: str | None) -> list[str]:
    errors: list[str] = []
    area = db.get(OracleWorkArea, work_area) if work_area else None
    if not work_area:
        errors.append("Oracle WORK_AREA mapping is missing")
    elif area is None or not area.active:
        errors.append("Oracle WORK_AREA is missing or inactive in the HR-Path catalogue")
    machine_row = db.get(OracleMachine, machine) if machine else None
    if not machine:
        errors.append("Oracle MACHINE mapping is missing")
    elif machine_row is None or not machine_row.active:
        errors.append("Oracle MACHINE is not in the HR-Path catalogue or is inactive")
    elif work_area and machine_row.work_area_code != work_area:
        errors.append("Oracle MACHINE does not belong to WORK_AREA")
    return errors


def structure_mapping_errors(db: Session, *, work_area: str | None, machine: str | None, cell: str | None) -> list[str]:
    errors = structure_parent_mapping_errors(db, work_area=work_area, machine=machine)
    cell_row = db.get(OracleCell, cell) if cell else None
    if not cell:
        errors.append("Oracle CELL mapping is missing")
    elif cell_row is None or not cell_row.active:
        errors.append("Oracle CELL is not in the HR-Path catalogue or is inactive")
    elif machine and cell_row.machine_code != machine:
        errors.append("Oracle CELL does not belong to MACHINE")
    return errors


def payroll_time_type_is_active(db: Session, code: str | None) -> bool:
    row = db.get(OraclePayrollTimeType, code) if code else None
    return bool(row and row.active)
