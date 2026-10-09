from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.admin import EventRead


class EventSnapshot(EventRead):
    model_config = ConfigDict(from_attributes=True)
    terminal_id: int
    action_id: int
    event_timezone: str
    oracle_attributes: dict[str, Any]
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
    worker_state: str
    event: EventSnapshot


class CardPage(BaseModel):
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
    oracle_payload_preview: dict[str, Any]
