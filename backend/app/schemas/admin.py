from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.domain.enums import IdentificationMode, StateEffect


class TerminalSettings(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=160)
    perimeter_only: bool | None = None
    external_device_id: str | None = Field(default=None, min_length=1, max_length=40)
    identification_mode: IdentificationMode = IdentificationMode.BOTH
    exit_menu_timeout_seconds: int | None = Field(default=None, ge=0, le=120)
    oracle_attributes: dict[str, Any] = Field(default_factory=dict)
    active: bool = True
    project_line_id: int | None = None
    workshop_id: int | None = None
    subworkshop_id: int | None = None
    action_codes: list[str] = Field(default_factory=list)
    exit_policy_mode: Literal["DISABLED", "SAME_TERMINAL", "SAME_WORK_CELL", "INHERIT"] | None = None

    @field_validator("oracle_attributes")
    @classmethod
    def validate_work_cell(cls, attributes):
        if "work_cell" in attributes:
            value = attributes["work_cell"]
            if not isinstance(value, str) or not 0 < len(value.strip()) <= 64:
                raise ValueError("work_cell must be a non-empty string of at most 64 characters; remove the key to leave it unconfigured")
            attributes = {**attributes, "work_cell": value.strip()}
        return attributes


class TerminalCreate(TerminalSettings):
    # Optional only for migration/test compatibility. Normal administration omits it
    # and the backend allocates an immutable application-managed code.
    code: str | None = Field(default=None, min_length=1, max_length=64)


class TerminalRead(BaseModel):
    factory_code: str = 'DEFAULT'
    terminal_role: str = 'CELL'
    code: str
    name: str
    external_device_id: str
    identification_mode: str
    exit_menu_timeout_seconds: int = 5
    reporter_id_type: str
    oracle_attributes: dict[str, Any]
    active: bool
    action_codes: list[str]
    provisioned: bool
    activation_pending: bool
    activation_token: str | None = None
    project_line_id: int | None = None
    workshop_id: int | None = None
    subworkshop_id: int | None = None
    structure_path: str | None = None
    exit_policy_mode: str
    effective_exit_policy_mode: str
    global_exit_policy_mode: str


class TerminalActionsUpdate(BaseModel):
    action_codes: list[str]


class TerminalProvisioningRead(BaseModel):
    code: str
    activation_token: str


class TerminalPairingApproval(BaseModel):
    pairing_code: str = Field(min_length=8, max_length=16)


class OracleCredentialsUpdate(BaseModel):
    auth_mode: Literal["none", "basic", "bearer"]
    username: str | None = Field(default=None, max_length=256)
    password: SecretStr | None = Field(default=None, max_length=4096)
    bearer_token: SecretStr | None = Field(default=None, max_length=8192)
    clear_credentials: bool = False

    @field_validator("username")
    @classmethod
    def strip_username(cls, value):
        return value.strip() if value is not None else value


class ActionSettings(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    label: str = Field(min_length=1, max_length=120)
    supplier_device_event: str = Field(min_length=1, max_length=40)
    oracle_supplier_event: str | None = Field(default=None, min_length=1, max_length=40)
    state_effect: StateEffect
    oracle_payroll_time_type: str | None = Field(default=None, max_length=120)
    oracle_attributes: dict[str, Any] = Field(default_factory=dict)
    display_order: int = Field(default=100, ge=0, le=100000)
    visual_key: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9-]+$")
    requires_subaction: bool = False
    parent_action_code: str | None = Field(default=None, max_length=64)
    show_on_terminal: bool = True
    active: bool = True


class ActionCreate(ActionSettings):
    code: str = Field(min_length=1, max_length=64)


class ActionRead(BaseModel):
    code: str
    label: str
    supplier_device_event: str
    oracle_supplier_event: str
    state_effect: str
    oracle_payroll_time_type: str | None = None
    oracle_attributes: dict[str, Any]
    display_order: int
    requires_subaction: bool
    parent_action_code: str | None
    subaction_codes: list[str]
    visual_key: str | None = None
    show_on_terminal: bool = True
    active: bool


class EventRead(BaseModel):
    id: str
    request_number: str
    terminal_code: str
    device_id: str
    action_code: str
    action_label: str
    supplier_device_event: str
    oracle_supplier_event: str | None = None
    state_effect: str
    reporter_id: str
    reporter_id_type: str
    identification_method: str
    source_person_id: str | None = None
    person_id: str | None = None
    credential_id: str | None = None
    oracle_reporter_id: str | None = None
    oracle_reporter_id_type: str | None = None
    oracle_payroll_time_type: str | None = None
    oracle_mapping_error: str | None = None
    event_datetime: datetime
    oracle_attributes: dict[str, Any]
    workshop_code: str | None = None
    workshop_description: str | None = None
    subworkshop_code: str | None = None
    subworkshop_description: str | None = None
    project_line_code: str | None = None
    project_line_description: str | None = None
    delivery_status: str
    attempt_count: int
    sent_at: datetime | None
    oracle_request_id: str | None
    oracle_event_id: str | None
