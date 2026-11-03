"""One shared readiness check for frozen Oracle Time Event snapshots."""

from app.services.oracle_catalogue import payroll_time_type_is_active, structure_mapping_errors

SUPPLIER_EVENT_BY_DIRECTION = {
    "ENTER": "HUT_TCD_SUPP1_IN_2",
    "EXIT": "HUT_TCD_SUPP1_OUT_2",
}


def action_readiness_errors(action, db) -> list[str]:
    errors: list[str] = []
    payroll = getattr(action, "oracle_payroll_time_type", None)
    if not payroll_time_type_is_active(db, payroll):
        errors.append("PayrollTimeType is missing or not in the HR-Path catalogue")
    expected = SUPPLIER_EVENT_BY_DIRECTION.get(getattr(action, "state_effect", None))
    if expected is None or getattr(action, "oracle_supplier_event", None) != expected:
        errors.append("Oracle supplier event/direction mapping is invalid")
    return errors


def oracle_readiness_errors(event, db) -> list[str]:
    if getattr(event, "delivery_status", None) == "LOCAL_ONLY":
        return ["Perimeter event is LOCAL_ONLY"]
    errors: list[str] = []
    if not (getattr(event, "person_id", None) or "").strip():
        errors.append("Resolved Person ID is missing")
    request_number = getattr(event, "request_number", None)
    if not request_number or len(request_number) > 80 or not request_number.strip():
        errors.append("Oracle requestNumber is missing or invalid (maximum 80 characters)")
    payroll = getattr(event, "oracle_payroll_time_type", None)
    if not payroll_time_type_is_active(db, payroll):
        errors.append("PayrollTimeType is missing or not in the HR-Path catalogue")
    errors.extend(structure_mapping_errors(db,
        work_area=getattr(event, "oracle_work_area_code", None),
        machine=getattr(event, "oracle_machine_code", None),
        cell=getattr(event, "oracle_cell_code", None),
    ))
    direction = getattr(event, "state_effect", None)
    expected = SUPPLIER_EVENT_BY_DIRECTION.get(direction)
    if expected is None or getattr(event, "oracle_supplier_event", None) != expected:
        errors.append("Oracle supplier event/direction mapping is invalid")
    return errors


def is_oracle_ready(event, db) -> bool:
    return not oracle_readiness_errors(event, db)
