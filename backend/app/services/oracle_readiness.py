"""One shared readiness check for frozen Oracle Time Event snapshots."""

from app.services.oracle_catalogue import CELLS, MACHINES, PAYROLL_TIME_TYPES, WORK_AREAS

SUPPLIER_EVENT_BY_DIRECTION = {
    "ENTER": "HUT_TCD_SUPP1_IN_2",
    "EXIT": "HUT_TCD_SUPP1_OUT_2",
}


def action_readiness_errors(action) -> list[str]:
    errors: list[str] = []
    payroll = getattr(action, "oracle_payroll_time_type", None)
    if payroll not in PAYROLL_TIME_TYPES:
        errors.append("PayrollTimeType is missing or not in the HR-Path catalogue")
    expected = SUPPLIER_EVENT_BY_DIRECTION.get(getattr(action, "state_effect", None))
    if expected is None or getattr(action, "oracle_supplier_event", None) != expected:
        errors.append("Oracle supplier event/direction mapping is invalid")
    return errors


def oracle_readiness_errors(event) -> list[str]:
    if getattr(event, "delivery_status", None) == "LOCAL_ONLY":
        return ["Perimeter event is LOCAL_ONLY"]
    errors: list[str] = []
    if not (getattr(event, "person_id", None) or "").strip():
        errors.append("Resolved Person ID is missing")
    request_number = getattr(event, "request_number", None)
    if not request_number or len(request_number) > 80 or not request_number.strip():
        errors.append("Oracle requestNumber is missing or invalid (maximum 80 characters)")
    payroll = getattr(event, "oracle_payroll_time_type", None)
    if payroll not in PAYROLL_TIME_TYPES:
        errors.append("PayrollTimeType is missing or not in the HR-Path catalogue")
    errors.extend(structure_mapping_errors(
        work_area=getattr(event, "oracle_work_area_code", None),
        machine=getattr(event, "oracle_machine_code", None),
        cell=getattr(event, "oracle_cell_code", None),
    ))
    direction = getattr(event, "state_effect", None)
    expected = SUPPLIER_EVENT_BY_DIRECTION.get(direction)
    if expected is None or getattr(event, "oracle_supplier_event", None) != expected:
        errors.append("Oracle supplier event/direction mapping is invalid")
    return errors


def structure_mapping_errors(*, work_area: str | None, machine: str | None, cell: str | None) -> list[str]:
    """Validate configured structure mapping values and hierarchy."""
    errors = structure_parent_mapping_errors(work_area=work_area, machine=machine)
    if not cell:
        errors.append("Oracle CELL mapping is missing")
    elif cell not in CELLS:
        errors.append("Oracle CELL is not in the HR-Path catalogue")
    elif machine and CELLS[cell]["machine"] != machine:
        errors.append("Oracle CELL does not belong to MACHINE")
    return errors


def structure_parent_mapping_errors(*, work_area: str | None, machine: str | None) -> list[str]:
    """Validate the WORK_AREA → MACHINE prefix of a structure path."""
    errors: list[str] = []
    if not work_area:
        errors.append("Oracle WORK_AREA mapping is missing")
    elif work_area not in WORK_AREAS:
        errors.append("Oracle WORK_AREA is not in the HR-Path catalogue")
    if not machine:
        errors.append("Oracle MACHINE mapping is missing")
    elif machine not in MACHINES:
        errors.append("Oracle MACHINE is not in the HR-Path catalogue")
    elif work_area and MACHINES[machine]["work_area"] != work_area:
        errors.append("Oracle MACHINE does not belong to WORK_AREA")
    return errors


def is_oracle_ready(event) -> bool:
    return not oracle_readiness_errors(event)
