from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import IdentificationMode, StateEffect


class TerminalSettings(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=160)
    external_device_id: str = Field(min_length=1, max_length=128)
    identification_mode: IdentificationMode = IdentificationMode.BOTH
    active: bool = True
    action_codes: list[str] = Field(default_factory=list)


class TerminalCreate(TerminalSettings):
    code: str = Field(min_length=1, max_length=64)


class TerminalRead(BaseModel):
    code: str
    name: str
    external_device_id: str
    identification_mode: str
    active: bool
    action_codes: list[str]


class TerminalActionsUpdate(BaseModel):
    action_codes: list[str]


class ActionSettings(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    label: str = Field(min_length=1, max_length=120)
    supplier_device_event: str = Field(min_length=1, max_length=128)
    state_effect: StateEffect
    reporter_id_type: str = Field(default="BADGE", min_length=1, max_length=16)
    oracle_attributes: dict[str, Any] = Field(default_factory=dict)
    display_order: int = Field(default=100, ge=0, le=100000)
    active: bool = True


class ActionCreate(ActionSettings):
    code: str = Field(min_length=1, max_length=64)


class ActionRead(BaseModel):
    code: str
    label: str
    supplier_device_event: str
    state_effect: str
    reporter_id_type: str
    oracle_attributes: dict[str, Any]
    display_order: int
    active: bool


class EventRead(BaseModel):
    id: str
    request_number: str
    terminal_code: str
    device_id: str
    action_code: str
    action_label: str
    supplier_device_event: str
    state_effect: str
    reporter_id: str
    reporter_id_type: str
    identification_method: str
    event_datetime: datetime
    delivery_status: str
    attempt_count: int
    sent_at: datetime | None
    oracle_request_id: str | None
    oracle_event_id: str | None
