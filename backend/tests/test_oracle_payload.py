from datetime import datetime, timezone

from app.integrations.oracle.client import OracleClient
from app.models.time_event import TimeEvent


def test_oracle_payload_contains_tcd_contract():
    event = TimeEvent(
        id="00000000-0000-0000-0000-000000000001",
        request_number="BSS-DEMO-01-1",
        terminal_id=1,
        action_id=1,
        terminal_code="DEMO-01",
        device_id="DEMO-01",
        action_code="START_WORK",
        action_label="Start work",
        supplier_device_event="BSS_START_WORK",
        state_effect="ENTER",
        reporter_id="84729",
        reporter_id_type="BADGE",
        identification_method="KEYPAD",
        event_datetime=datetime(2026, 10, 9, 16, 0, tzinfo=timezone.utc),
        event_timezone="Europe/Madrid",
        oracle_attributes={},
        delivery_status="PENDING",
    )
    payload = OracleClient().build_payload(event)
    item = payload["timeEvents"][0]
    assert payload["requestNumber"] == "BSS-DEMO-01-1"
    assert item["deviceId"] == "DEMO-01"
    assert item["reporterId"] == "84729"
    assert item["reporterIdType"] == "BADGE"
    assert item["supplierDeviceEvent"] == "BSS_START_WORK"
    assert item["eventDateTime"].endswith("+02:00")
