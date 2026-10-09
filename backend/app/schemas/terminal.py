from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import IdentificationMethod


class TerminalAction(BaseModel):
    code: str
    label: str


class TerminalConfig(BaseModel):
    code: str
    name: str
    identification_mode: str
    actions: list[TerminalAction]


class ScanRequest(BaseModel):
    reporter_id: str = Field(min_length=1, max_length=160)
    identification_method: IdentificationMethod


class ExitRequest(ScanRequest):
    action_code: str


class CapturedEvent(BaseModel):
    id: str
    action_code: str
    action_label: str
    event_datetime: datetime
    delivery_status: str


class ScanResponse(BaseModel):
    flow: str
    worker_state: str
    event: CapturedEvent | None = None
    actions: list[TerminalAction] = []
