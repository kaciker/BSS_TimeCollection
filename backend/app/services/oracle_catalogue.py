"""Explicit HR-Path Oracle values currently verified for CORP.

Only values evidenced in the approved HR-Path mapping data are listed here.
Unknown catalogue entries must remain unmapped until added from the workbook.
"""

PAYROLL_TIME_TYPES = (
    "Public Holiday ES",
    "Workshop Entry ES",
    "Project Entry ES",
    "Non-productive time ES",
    "Break ES",
)

WORK_AREAS = {"439": "Acabado TP"}
MACHINES = {
    "4391": {"description": "T439.1", "work_area": "439"},
    "4392": {"description": "T439.2", "work_area": "439"},
    "4393": {"description": "T439.3 Recambios", "work_area": "439"},
}
CELLS = {
    # Oracle exposes one P24 G.V. cell; BSS right/left details remain local.
    "54Q": {"description": "G.V. D34", "machine": "4391"},
    "54T": {"description": "G.V. P24", "machine": "4391"},
}


def catalogue_payload() -> dict:
    return {
        "payroll_time_types": list(PAYROLL_TIME_TYPES),
        "work_areas": [{"code": code, "description": description} for code, description in WORK_AREAS.items()],
        "machines": [{"code": code, **value} for code, value in MACHINES.items()],
        "cells": [{"code": code, **value} for code, value in CELLS.items()],
    }
