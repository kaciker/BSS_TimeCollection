from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.admin import EventRead


class EventSnapshot(EventRead):
    model_config = ConfigDict(from_attributes=True)
    event_kind: str = "CELL"
    factory_code: str | None = None
    correlation_id: str | None = None
    auto_cell_exit_event_id: str | None = None
    terminal_id: int
    action_id: int | None
    request_number: str | None = None
    device_id: str | None = None
    supplier_device_event: str | None = None
    reporter_id_type: str | None = None
    identification_method: str | None = None
    event_timezone: str
    oracle_attributes: dict[str, Any]
    oracle_payroll_time_type: str | None = None
    oracle_mapping_error: str | None = None
    created_at: datetime
    next_attempt_at: datetime | None
    last_attempt_at: datetime | None


class AttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_id: str
    attempt_number: int
    started_at: datetime
    finished_at: datetime
    endpoint: str
    http_status: int | None
    result: str
    duration_ms: int
    request_payload: dict[str, Any]
    response_payload: Any | None
    error_message: str | None


class EventPage(BaseModel):
    items: list[EventSnapshot]
    total: int


class CardState(BaseModel):
    reporter_id: str
    source_person_id: str | None = None
    person_id: str | None = None
    credential_id: str | None = None
    worker_state: str
    factory_code: str | None = None
    factory_state: str | None = None
    event: EventSnapshot


class CardPage(BaseModel):
    factory_perimeter_enabled: bool = False
    items: list[CardState]
    total: int


class AttemptSummary(AttemptRead):
    reporter_id: str
    terminal_code: str


class AttemptPage(BaseModel):
    items: list[AttemptSummary]
    total: int


class EventDetail(BaseModel):
    event: EventSnapshot
    attempts: list[AttemptRead]
    oracle_enabled: bool
    oracle_payload_preview: dict[str, Any] | None
    oracle_mapping_error: str | None = None
