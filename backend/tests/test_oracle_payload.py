from datetime import datetime, timezone
import pytest
import httpx

from app.integrations.oracle.client import OracleClient
from app.core.config import settings
from app.integrations.oracle.client import OracleMappingError
from app.models.time_event import TimeEvent


def test_oracle_payload_matches_validated_dev2_contract_and_uses_capture_time():
    event = TimeEvent(
        id="00000000-0000-0000-0000-000000000001",
        request_number="BSS-DEMO-01-1",
        terminal_id=1,
        action_id=1,
        terminal_code="DEMO-01",
        device_id="LOCAL-DEVICE-ID",
        action_code="START_WORK",
        action_label="Start work",
        supplier_device_event="BSS_START_WORK",
        oracle_supplier_event="HUT_TCD_SUPP1_IN_2",
        state_effect="ENTER",
        reporter_id="0582609699",
        reporter_id_type="BADGE",
        person_id="84729",
        oracle_reporter_id="SHOULD-NOT-BE-USED",
        oracle_reporter_id_type="BADGE",
        identification_method="KEYPAD",
        event_datetime=datetime(2026, 10, 9, 16, 0, 0, 123456, tzinfo=timezone.utc),
        event_timezone="Europe/Madrid",
        oracle_attributes={"work_cell": "LOCAL", "reason": "SHIFT", "custom": "LOCAL-ONLY"},
        workshop_code="439", subworkshop_code="4393", project_line_code="54A",
        oracle_payroll_time_type="Workshop Entry ES",
        delivery_status="PENDING",
    )
    payload = OracleClient().build_payload(event)
    item = payload["timeEvents"][0]
    assert payload["requestNumber"] == "BSS-DEMO-01-1"
    assert payload["sourceId"] == "HUT_TCD_SUPP1"
    assert payload["requestTimestamp"] == "2026-10-09T16:00:00.123Z"
    assert item["eventDateTime"] == payload["requestTimestamp"]
    assert "deviceId" not in item
    assert item["reporterId"] == "84729"
    assert item["reporterIdType"] == "PERSON"
    assert item["supplierDeviceEvent"] == "HUT_TCD_SUPP1_IN_2"
    assert item["timeEventAttributes"] == [
        {"name": "PayrollTimeType", "value": "Workshop Entry ES"},
        {"name": "WORK_AREA", "value": "439"},
        {"name": "MACHINE", "value": "4393"},
        {"name": "CELL", "value": "54A"},
    ]
    assert event.device_id == "LOCAL-DEVICE-ID"
    assert event.oracle_attributes == {"work_cell": "LOCAL", "reason": "SHIFT", "custom": "LOCAL-ONLY"}
    assert settings.oracle_enabled is False
    assert OracleClient().endpoint == "https://fa-eocc-dev2-saasfaprod1.fa.ocs.oraclecloud.com/hcmRestApi/resources/11.13.18.05/timeEventRequests"
    assert OracleClient()._headers()["REST-Framework-Version"] == "4"
    assert OracleClient()._headers()["Content-Type"] == "application/json"
    assert OracleClient()._headers()["Accept"] == "application/json"


def test_missing_person_id_and_incomplete_structure_never_create_payload():
    event = TimeEvent(
        id="00000000-0000-0000-0000-000000000002", request_number="BSS-NO-PERSON", terminal_id=1,
        action_id=1, terminal_code="DEMO", device_id="DEMO", action_code="START", action_label="Start",
        supplier_device_event="HUT_TCD_SUPP1_IN_2", state_effect="ENTER", reporter_id="RAW-RFID-999",
        oracle_supplier_event="HUT_TCD_SUPP1_IN_2",
        reporter_id_type="PERSON", identification_method="RFID", person_id=None, oracle_reporter_id=None,
        event_datetime=datetime(2026, 10, 9, 16, 0, tzinfo=timezone.utc), event_timezone="Europe/Madrid",
        oracle_attributes={}, workshop_code="439", subworkshop_code="4393", project_line_code="54A",
        delivery_status="PENDING",
    )
    with pytest.raises(OracleMappingError, match="Person ID"):
        OracleClient().build_payload(event)
    # The badge remains stored locally for audit, while serialization is
    # blocked before any HTTP transmission can occur.
    assert event.reporter_id == "RAW-RFID-999"


@pytest.mark.parametrize(
    ("request_number", "attributes", "expected_error"),
    [
        ("R" * 81, {}, "requestNumber exceeds.*80-character"),
    ],
)
def test_oracle_describe_field_limits_block_invalid_payload(request_number, attributes, expected_error):
    event = TimeEvent(
        id="limit-event", request_number=request_number, terminal_id=1, action_id=1,
        terminal_code="T", device_id="D", action_code="START", action_label="Start",
        supplier_device_event="BSS_START", oracle_supplier_event="HUT_TCD_SUPP1_IN_2",
        state_effect="ENTER", reporter_id="badge", reporter_id_type="BADGE", person_id="P1",
        identification_method="RFID", event_datetime=datetime(2026, 10, 30, 8, tzinfo=timezone.utc),
        event_timezone="UTC", oracle_attributes=attributes, oracle_payroll_time_type="TYPE", workshop_code="W",
        subworkshop_code="S", project_line_code="P", delivery_status="PENDING",
    )
    with pytest.raises(OracleMappingError, match=expected_error):
        OracleClient().build_payload(event)


def test_send_uses_basic_auth_framework_header_and_mocked_http(monkeypatch):
    import app.integrations.oracle.client as oracle
    captured = {}

    class Response:
        status_code = 201
        text = '{"timeEventRequestId":"mocked"}'
        def json(self): return {"timeEventRequestId": "mocked"}

    class Client:
        def __init__(self, **kwargs): captured["timeout"] = kwargs["timeout"]
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, endpoint, **kwargs):
            captured.update(endpoint=endpoint, **kwargs)
            return Response()

    monkeypatch.setattr(oracle.httpx, "Client", Client)
    monkeypatch.setattr(settings, "oracle_username", "test-user")
    monkeypatch.setattr(settings, "oracle_password", "test-secret")
    event = TimeEvent(
        id="id", request_number="mocked", terminal_id=1, action_id=1, terminal_code="T", device_id="D",
        action_code="A", action_label="A", supplier_device_event="HUT_TCD_SUPP1_IN_2", state_effect="ENTER",
        oracle_supplier_event="HUT_TCD_SUPP1_IN_2",
        reporter_id="raw-badge", reporter_id_type="PERSON", person_id="104582", oracle_reporter_id="104582",
        identification_method="RFID", event_datetime=datetime(2026,10,9,12,tzinfo=timezone.utc), event_timezone="UTC",
        oracle_attributes={}, oracle_payroll_time_type="TYPE", workshop_code="439", subworkshop_code="4393", project_line_code="54A", delivery_status="PENDING",
    )
    result = OracleClient().send(event)
    assert result.result == "SENT"
    assert captured["endpoint"] == OracleClient().endpoint
    assert isinstance(captured["auth"], httpx.BasicAuth)
    assert captured["headers"]["REST-Framework-Version"] == "4"
    assert captured["json"]["timeEvents"][0]["reporterId"] == "104582"
    assert captured["json"]["requestTimestamp"] == captured["json"]["timeEvents"][0]["eventDateTime"]
    assert result.oracle_request_id == "mocked"


def test_send_uses_bearer_auth_and_keeps_event_time_offset(monkeypatch, tmp_path):
    import app.integrations.oracle.client as oracle
    from app.core.oracle_credentials import configure_oracle_credentials

    calls = []

    class Response:
        status_code = 201

        def json(self):
            return {"timeEventRequestId": 123, "timeEvents": [{"timeEventId": 456}]}

    class Client:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def post(self, endpoint, **kwargs):
            calls.append((endpoint, kwargs))
            return Response()

    monkeypatch.setattr(settings, "oracle_credentials_file", str(tmp_path / "credentials.json"))
    configure_oracle_credentials(
        auth_mode="bearer", username=None, password=None, bearer_token="mock-bearer-secret"
    )
    monkeypatch.setattr(oracle.httpx, "Client", Client)
    event = TimeEvent(
        id="bearer-event", request_number="BSS-bearer", terminal_id=1, action_id=1,
        terminal_code="T", device_id="D", action_code="START", action_label="Start",
        supplier_device_event="BSS_START", oracle_supplier_event="HUT_TCD_SUPP1_IN_2",
        state_effect="ENTER", reporter_id="local-badge", reporter_id_type="BADGE",
        person_id="104582", identification_method="RFID",
        event_datetime=datetime(2026, 10, 30, 8, 0, tzinfo=timezone.utc),
        event_timezone="Europe/Madrid", oracle_attributes={}, oracle_payroll_time_type="TYPE", workshop_code="439",
        subworkshop_code="4393", project_line_code="54A", delivery_status="PENDING",
    )

    result = OracleClient().send(event)

    assert result.result == "SENT"
    assert result.oracle_request_id == 123
    assert result.oracle_event_id == 456
    endpoint, kwargs = calls[0]
    assert endpoint == OracleClient().endpoint
    assert kwargs["headers"]["Authorization"] == "Bearer mock-bearer-secret"
    assert kwargs["auth"] is None
    assert kwargs["json"]["timeEvents"][0]["eventDateTime"] == "2026-10-30T08:00:00.000Z"
    assert kwargs["json"]["requestTimestamp"] == kwargs["json"]["timeEvents"][0]["eventDateTime"]
    assert kwargs["json"]["requestNumber"] == "BSS-bearer"


@pytest.mark.parametrize(
    ("status_code", "expected_status", "retryable"),
    [(400, "REJECTED", False), (408, "UNKNOWN", False), (425, "RETRY", True), (429, "RETRY", True), (500, "UNKNOWN", False), (503, "UNKNOWN", False)],
)
def test_send_classifies_mocked_oracle_http_errors(monkeypatch, status_code, expected_status, retryable):
    import app.integrations.oracle.client as oracle

    class Response:
        def __init__(self, status): self.status_code = status
        def json(self): return {"title": "synthetic validation error", "status": status_code}

    class Client:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def post(self, *_args, **_kwargs): return Response(status_code)

    monkeypatch.setattr(oracle.httpx, "Client", Client)
    event = TimeEvent(
        id="error-event", request_number="BSS-error", terminal_id=1, action_id=1,
        terminal_code="T", device_id="D", action_code="START", action_label="Start",
        supplier_device_event="BSS_START", oracle_supplier_event="HUT_TCD_SUPP1_IN_2",
        state_effect="ENTER", reporter_id="badge", reporter_id_type="BADGE", person_id="P1",
        identification_method="RFID", event_datetime=datetime(2026, 10, 30, 8, tzinfo=timezone.utc),
        event_timezone="UTC", oracle_attributes={}, oracle_payroll_time_type="TYPE", workshop_code="W", subworkshop_code="S",
        project_line_code="P", delivery_status="PENDING",
    )

    result = OracleClient().send(event)
    assert result.result == expected_status
    assert result.retryable is retryable
    assert result.ambiguous is (status_code in {408, 500, 503})
    assert result.response_payload["title"] == "synthetic validation error"


def test_incomplete_structure_snapshot_blocks_payload_before_http():
    event = TimeEvent(
        id="id", request_number="incomplete", terminal_id=1, action_id=1, terminal_code="T", device_id="D",
        action_code="A", action_label="A", supplier_device_event="HUT_TCD_SUPP1_IN_2", state_effect="ENTER",
        oracle_supplier_event="HUT_TCD_SUPP1_IN_2",
        reporter_id="raw", reporter_id_type="PERSON", person_id="104582", identification_method="RFID",
        event_datetime=datetime(2026,10,9,12,tzinfo=timezone.utc), event_timezone="UTC", oracle_attributes={},
        workshop_code="439", subworkshop_code=None, project_line_code="54A", delivery_status="PENDING",
    )
    with pytest.raises(OracleMappingError, match="snapshot is incomplete"):
        OracleClient().build_payload(event)


def test_exit_payload_uses_direction_mapping_and_preserves_local_event():
    event = TimeEvent(
        id="exit-id", request_number="BSS-DEMO-EXIT", terminal_id=1, action_id=2,
        terminal_code="DEMO", device_id="DEMO", action_code="BREAK", action_label="Break",
        supplier_device_event="BSS_BREAK", oracle_supplier_event="HUT_TCD_SUPP1_OUT_2",
        state_effect="EXIT", reporter_id="raw-badge", reporter_id_type="PERSON", person_id="104582",
        identification_method="RFID", event_datetime=datetime(2026, 10, 9, 12, tzinfo=timezone.utc),
        event_timezone="UTC", oracle_attributes={}, workshop_code="439", subworkshop_code="4393",
        project_line_code="54A", oracle_payroll_time_type="Break ES", delivery_status="PENDING",
    )
    item = OracleClient().build_payload(event)["timeEvents"][0]
    assert item["supplierDeviceEvent"] == "HUT_TCD_SUPP1_OUT_2"
    assert item["reporterId"] == "104582"
    assert {row["name"]: row["value"] for row in item["timeEventAttributes"]}["PayrollTimeType"] == "Break ES"
    assert event.supplier_device_event == "BSS_BREAK"


def test_missing_person_id_is_held_without_http(monkeypatch):
    import app.integrations.oracle.client as oracle

    def forbidden_client(*args, **kwargs):
        raise AssertionError("A missing Person ID must never reach Oracle HTTP")

    monkeypatch.setattr(oracle.httpx, "Client", forbidden_client)
    event = TimeEvent(
        id="no-person", request_number="BSS-NO-PERSON", terminal_id=1, action_id=1,
        terminal_code="DEMO", device_id="DEMO", action_code="START", action_label="Start",
        supplier_device_event="BSS_START", oracle_supplier_event="HUT_TCD_SUPP1_IN_2", state_effect="ENTER",
        reporter_id="RAW-RFID-999", reporter_id_type="PERSON", person_id=None,
        identification_method="RFID", event_datetime=datetime(2026, 10, 9, 12, tzinfo=timezone.utc),
        event_timezone="UTC", oracle_attributes={}, workshop_code="439", subworkshop_code="4393",
        project_line_code="54A", delivery_status="PENDING",
    )
    with pytest.raises(OracleMappingError, match="Person ID"):
        OracleClient().send(event)
    assert event.reporter_id == "RAW-RFID-999"


def test_request_number_over_oracle_limit_is_blocked_before_serialization():
    event = TimeEvent(
        id="long-request", request_number="R" * 81, terminal_id=1, action_id=1,
        terminal_code="DEMO", device_id="DEMO", action_code="START", action_label="Start",
        supplier_device_event="BSS_START", oracle_supplier_event="HUT_TCD_SUPP1_IN_2",
        state_effect="ENTER", reporter_id="raw-badge", reporter_id_type="BADGE",
        person_id="104582", identification_method="RFID",
        event_datetime=datetime(2026, 10, 9, 12, tzinfo=timezone.utc), event_timezone="UTC",
        oracle_attributes={}, workshop_code="439", subworkshop_code="4393",
        project_line_code="54A", delivery_status="PENDING",
    )
    with pytest.raises(OracleMappingError, match="requestNumber.*80-character"):
        OracleClient().build_payload(event)


@pytest.mark.parametrize(("status_code", "result_name", "retryable", "ambiguous"), [
    (408, "UNKNOWN", False, True), (425, "RETRY", True, False),
    (429, "RETRY", True, False), (500, "UNKNOWN", False, True),
    (503, "UNKNOWN", False, True), (400, "REJECTED", False, False),
])
def test_post_response_classification_does_not_replay_ambiguous_requests(
    monkeypatch, status_code, result_name, retryable, ambiguous
):
    import app.integrations.oracle.client as oracle

    class Response:
        text = "{}"
        def json(self): return {}

    class Client:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def post(self, *_args, **_kwargs):
            response = Response()
            response.status_code = status_code
            return response

    monkeypatch.setattr(oracle.httpx, "Client", Client)
    event = TimeEvent(
        id="delivery-classification", request_number="BSS-DEMO-1", terminal_id=1, action_id=1,
        terminal_code="DEMO", device_id="DEMO", action_code="START", action_label="Start",
        supplier_device_event="BSS_START", oracle_supplier_event="HUT_TCD_SUPP1_IN_2",
        state_effect="ENTER", reporter_id="raw-badge", reporter_id_type="BADGE",
        person_id="104582", identification_method="RFID",
        event_datetime=datetime(2026, 10, 9, 12, tzinfo=timezone.utc), event_timezone="UTC",
        oracle_attributes={}, workshop_code="439", subworkshop_code="4393",
        oracle_payroll_time_type="TYPE", project_line_code="54A", delivery_status="PENDING",
    )
    result = OracleClient().send(event)
    assert result.result == result_name
    assert result.retryable is retryable
    assert result.ambiguous is ambiguous


@pytest.mark.parametrize("missing", ["payroll", "person", "workshop", "subworkshop", "project_line"])
def test_missing_required_oracle_mapping_blocks_serialization_and_transmission(missing, monkeypatch):
    values = dict(
        id="required-fields", request_number="BSS-required-fields", terminal_id=1, action_id=1,
        terminal_code="T", device_id="D", action_code="START", action_label="Start",
        supplier_device_event="BSS_START", oracle_supplier_event="HUT_TCD_SUPP1_IN_2",
        state_effect="ENTER", reporter_id="raw-card", reporter_id_type="BADGE",
        person_id="104582", identification_method="RFID",
        event_datetime=datetime(2026, 10, 9, 12, tzinfo=timezone.utc), event_timezone="UTC",
        oracle_attributes={"custom": "LOCAL"}, oracle_payroll_time_type="Workshop Entry ES",
        workshop_code="439", subworkshop_code="4393", project_line_code="54A", delivery_status="PENDING",
    )
    field = {"payroll": "oracle_payroll_time_type", "person": "person_id", "workshop": "workshop_code",
             "subworkshop": "subworkshop_code", "project_line": "project_line_code"}[missing]
    values[field] = None
    event = TimeEvent(**values)
    import app.integrations.oracle.client as oracle
    monkeypatch.setattr(oracle.httpx, "Client", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("Invalid Oracle mapping must be rejected before HTTP transmission")
    ))
    with pytest.raises(OracleMappingError):
        OracleClient().send(event)


def test_exit_supplier_mapping_is_explicit_and_direction_mismatch_is_blocked():
    event = TimeEvent(
        id="exit-id", request_number="BSS-EXIT", terminal_id=1, action_id=2, terminal_code="T", device_id="D",
        action_code="EXIT", action_label="Exit", supplier_device_event="BSS_EXIT",
        oracle_supplier_event="HUT_TCD_SUPP1_OUT_2", state_effect="EXIT", reporter_id="raw-card",
        reporter_id_type="BADGE", person_id="104582", identification_method="RFID",
        event_datetime=datetime(2026, 10, 9, 12, tzinfo=timezone.utc), event_timezone="UTC",
        oracle_attributes={}, oracle_payroll_time_type="Exit ES", workshop_code="439",
        subworkshop_code="4393", project_line_code="54A", delivery_status="PENDING",
    )
    item = OracleClient().build_payload(event)["timeEvents"][0]
    assert item["supplierDeviceEvent"] == "HUT_TCD_SUPP1_OUT_2"
    event.oracle_supplier_event = "HUT_TCD_SUPP1_IN_2"
    with pytest.raises(OracleMappingError, match="incompatible"):
        OracleClient().build_payload(event)


def test_naive_captured_datetime_uses_captured_timezone_then_normalizes_to_utc():
    event = TimeEvent(
        id="naive-time", request_number="BSS-naive", terminal_id=1, action_id=1, terminal_code="T", device_id="D",
        action_code="START", action_label="Start", supplier_device_event="BSS_START",
        oracle_supplier_event="HUT_TCD_SUPP1_IN_2", state_effect="ENTER", reporter_id="raw",
        reporter_id_type="BADGE", person_id="104582", identification_method="RFID",
        event_datetime=datetime(2026, 10, 9, 18, 0, 0, 999999), event_timezone="Europe/Madrid",
        oracle_attributes={}, oracle_payroll_time_type="Entry", workshop_code="439",
        subworkshop_code="4393", project_line_code="54A", delivery_status="PENDING",
    )
    payload = OracleClient().build_payload(event)
    assert payload["requestTimestamp"] == "2026-10-09T16:00:00.999Z"
    assert payload["timeEvents"][0]["eventDateTime"] == payload["requestTimestamp"]


@pytest.mark.parametrize("failure", [httpx.ReadTimeout("read"), httpx.WriteTimeout("write"), httpx.RemoteProtocolError("protocol")])
def test_timeout_or_post_send_protocol_failure_is_unknown_and_never_replayed(monkeypatch, failure):
    import app.integrations.oracle.client as oracle
    calls = []

    class Client:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def post(self, *_args, **_kwargs):
            calls.append("post")
            raise failure

    monkeypatch.setattr(oracle.httpx, "Client", Client)
    event = TimeEvent(
        id="ambiguous", request_number="BSS-ambiguous", terminal_id=1, action_id=1,
        terminal_code="T", device_id="LOCAL", action_code="START", action_label="Start",
        supplier_device_event="BSS_START", oracle_supplier_event="HUT_TCD_SUPP1_IN_2",
        state_effect="ENTER", reporter_id="raw-card", reporter_id_type="BADGE", person_id="104582",
        identification_method="RFID", event_datetime=datetime(2026, 10, 9, 12, tzinfo=timezone.utc),
        event_timezone="UTC", oracle_attributes={}, oracle_payroll_time_type="Entry",
        workshop_code="439", subworkshop_code="4393", project_line_code="54A", delivery_status="PENDING",
    )
    result = OracleClient().send(event)
    assert result.result == "UNKNOWN"
    assert result.retryable is False
    assert result.ambiguous is True
    assert calls == ["post"]


def test_connect_failure_is_retryable_before_transmission(monkeypatch):
    import app.integrations.oracle.client as oracle
    calls = []

    class Client:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def post(self, *_args, **_kwargs):
            calls.append("post")
            raise httpx.ConnectError("connect")

    monkeypatch.setattr(oracle.httpx, "Client", Client)
    event = TimeEvent(
        id="connect-failure", request_number="BSS-connect", terminal_id=1, action_id=1,
        terminal_code="T", device_id="LOCAL", action_code="START", action_label="Start",
        supplier_device_event="BSS_START", oracle_supplier_event="HUT_TCD_SUPP1_IN_2",
        state_effect="ENTER", reporter_id="raw-card", reporter_id_type="BADGE", person_id="104582",
        identification_method="RFID", event_datetime=datetime(2026, 10, 9, 12, tzinfo=timezone.utc),
        event_timezone="UTC", oracle_attributes={}, oracle_payroll_time_type="Entry",
        workshop_code="439", subworkshop_code="4393", project_line_code="54A", delivery_status="PENDING",
    )
    result = OracleClient().send(event)
    assert result.result == "RETRY"
    assert result.retryable is True
    assert result.ambiguous is False
    assert calls == ["post"]
