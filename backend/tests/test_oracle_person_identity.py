from datetime import datetime, timezone

from app.integrations.oracle.client import OracleClient
from app.models.time_event import TimeEvent


def test_oracle_payload_uses_frozen_person_identity_when_available():
    event = TimeEvent(
        id="00000000-0000-0000-0000-000000000099",
        request_number="BSS-DEMO-01-person",
        terminal_id=1,
        action_id=1,
        terminal_code="DEMO-01",
        device_id="DEMO-01",
        action_code="START_WORK",
        action_label="Start work",
        supplier_device_event="BSS_START_WORK",
        oracle_supplier_event="HUT_TCD_SUPP1_IN_2",
        state_effect="ENTER",
        reporter_id="0582609699",
        reporter_id_type="BADGE",
        identification_method="RFID",
        source_person_id="PERSON-PK-1",
        person_id="104582",
        credential_id="CARD-A",
        oracle_reporter_id="104582",
        oracle_reporter_id_type="PERSON",
        event_datetime=datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc),
        event_timezone="Europe/Madrid",
        oracle_attributes={},
        oracle_payroll_time_type="Workshop Entry ES",
        workshop_code="439",
        subworkshop_code="4393",
        project_line_code="54A",
        delivery_status="PENDING",
    )
    item = OracleClient().build_payload(event)["timeEvents"][0]
    assert item["reporterId"] == "104582"
    assert item["reporterIdType"] == "PERSON"
