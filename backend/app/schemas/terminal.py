from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import IdentificationMethod


class TerminalAction(BaseModel):
    code: str
    label: str
    has_subactions: bool = False
    visual_key: str | None = None


class TerminalConfig(BaseModel):
    code: str
    name: str
    identification_mode: str
    actions: list[TerminalAction]


class ActivationRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)


class PairingStartRead(BaseModel):
    pairing_code: str
    request_token: str
    expires_at: datetime
    poll_after_seconds: int = 2


class PairingPollRequest(BaseModel):
    request_token: str = Field(min_length=32, max_length=256)


class PairingPollRead(BaseModel):
    status: str
    config: TerminalConfig | None = None


class ScanRequest(BaseModel):
    reporter_id: str = Field(min_length=1, max_length=80)
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
    actions: list[TerminalAction] = Field(default_factory=list)
