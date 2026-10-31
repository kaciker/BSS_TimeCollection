from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
import httpx
import ssl
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session

from app.core.config import settings
from app.core.oracle_credentials import configure_oracle_credentials, credential_state, get_oracle_credentials
from app.db.session import get_db
from app.domain.enums import DeliveryStatus
from app.models.action import Action
from app.models.terminal import Terminal
from app.models.structure import ProjectLine
from app.models.terminal_pairing_request import TerminalPairingRequest
from app.models.time_event import TimeEvent
from app.schemas.admin import (
    ActionCreate,
    ActionRead,
    ActionSettings,
    EventRead,
    TerminalActionsUpdate,
    TerminalCreate,
    TerminalPairingApproval,
    TerminalProvisioningRead,
    TerminalRead,
    TerminalSettings,
    OracleCredentialsUpdate,
)
from app.services.configuration_service import (
    check_device_id,
    check_supplier_event,
    commit_configuration,
    resolve_actions,
    resolve_parent_action,
    validate_action_hierarchy,
    validate_actions,
)
from app.services.exit_policy import get_mode, save_mode, policies
from app.services.terminal_cloning_service import clone_terminal
from app.services.terminal_code_service import allocate_terminal_code
from app.services.terminal_identity_service import issue_activation_token
from app.services.terminal_pairing_service import approve_pairing_request

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])



def _resolve_structure(db: Session, leaf_id: int | None, workshop_id: int | None, subworkshop_id: int | None, *, required: bool) -> ProjectLine | None:
    if leaf_id is None:
        if required or workshop_id is not None or subworkshop_id is not None:
            raise HTTPException(422, "Select a complete Workshop / Subworkshop / Project / Line path")
        return None
    leaf = db.get(ProjectLine, leaf_id)
    if leaf is None or not leaf.active or not leaf.subworkshop.active or not leaf.subworkshop.workshop.active:
        raise HTTPException(422, "Project / Line path does not exist or is inactive")
    if subworkshop_id is not None and subworkshop_id != leaf.subworkshop_id:
        raise HTTPException(422, "Subworkshop does not match Project / Line")
    if workshop_id is not None and workshop_id != leaf.subworkshop.workshop_id:
        raise HTTPException(422, "Workshop does not match Project / Line")
    return leaf


def _commit_terminal_settings(db: Session, terminal: Terminal, mode: str | None) -> None:
    try:
        if mode is not None:
            db.flush()
            save_mode(db, terminal.id, mode, commit=False)
        commit_configuration(db)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Code, device ID or supplier event already exists")


def _terminal_read(terminal: Terminal, activation_token: str | None = None) -> TerminalRead:
    db = object_session(terminal)
    override = db.execute(select(policies.c.mode).where(policies.c.terminal_id == terminal.id)).scalar_one_or_none()
    return TerminalRead(
        factory_code=terminal.factory_code,
        terminal_role=terminal.terminal_role,
        code=terminal.code,
        name=terminal.name,
        external_device_id=terminal.external_device_id,
        identification_mode=terminal.identification_mode,
        exit_menu_timeout_seconds=terminal.exit_menu_timeout_seconds,
        reporter_id_type=settings.oracle_person_reporter_id_type,
        oracle_attributes=terminal.oracle_attributes or {},
        active=terminal.active,
        action_codes=sorted(action.code for action in terminal.actions),
        provisioned=bool(terminal.session_token_hash),
        activation_pending=bool(terminal.activation_token_hash),
        activation_token=activation_token,
        project_line_id=terminal.project_line_id,
        subworkshop_id=terminal.project_line.subworkshop_id if terminal.project_line else None,
        workshop_id=terminal.project_line.subworkshop.workshop_id if terminal.project_line else None,
        structure_path=" / ".join([terminal.project_line.subworkshop.workshop.code, terminal.project_line.subworkshop.code, terminal.project_line.code]) if terminal.project_line else None,
        exit_policy_mode=override or "INHERIT",
        effective_exit_policy_mode=get_mode(db, terminal.id),
        global_exit_policy_mode=get_mode(db, None),
    )


def _action_read(action: Action) -> ActionRead:
    return ActionRead(
        code=action.code,
        label=action.label,
        supplier_device_event=action.supplier_device_event,
        oracle_supplier_event=action.oracle_supplier_event,
        state_effect=action.state_effect,
        oracle_payroll_time_type=action.oracle_payroll_time_type,
        oracle_attributes=action.oracle_attributes or {},
        display_order=action.display_order,
        requires_subaction=action.requires_subaction,
        visual_key=action.visual_key,
        show_on_terminal=action.show_on_terminal,
        parent_action_code=action.parent_action.code if action.parent_action else None,
        subaction_codes=sorted(child.code for child in action.subactions),
        active=action.active,
    )


@router.get("/integration-settings")
def integration_settings():
    endpoint = f"{settings.oracle_base_url.rstrip('/')}{settings.oracle_api_path}"
    credential_status = credential_state()
    auth_mode = credential_status["auth_mode"]
    return {
        "oracle_enabled": settings.oracle_enabled,
        "base_url": settings.oracle_base_url,
        "api_path": settings.oracle_api_path,
        "endpoint": endpoint,
        "oracle_source_id": settings.oracle_source_id,
        "auth_mode": auth_mode,
        "username": credential_status["username"],
        "password": "Configured" if credential_status["password_configured"] else "Not configured",
        "bearer_token": "Configured" if credential_status["bearer_token_configured"] else "Not configured",
        "reporter_id_type": settings.oracle_person_reporter_id_type,
        "rest_framework_version": settings.oracle_rest_framework_version,
        "timeout_seconds": settings.oracle_timeout_seconds,
        "credentials_configured": credential_status["credentials_configured"],
        "connection_status": "Not tested; authentication can be checked using the read-only Oracle metadata endpoint.",
    }


@router.put("/integration-credentials")
def update_integration_credentials(payload: OracleCredentialsUpdate):
    try:
        state = configure_oracle_credentials(
            auth_mode=payload.auth_mode,
            username=payload.username,
            password=payload.password.get_secret_value() if payload.password is not None else None,
            bearer_token=payload.bearer_token.get_secret_value() if payload.bearer_token is not None else None,
            clear_credentials=payload.clear_credentials,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail="Oracle credentials could not be persisted securely.") from exc
    return {"saved": True, **state}


@router.post("/integration-authentication-test")
def integration_authentication_test():
    """Validate Oracle credentials using only the read-only resource metadata endpoint."""
    state = credential_state()
    credentials = get_oracle_credentials()
    auth_mode = state["auth_mode"]
    if not state["credentials_configured"]:
        return {
            "credentials_configured": False,
            "validated": False,
            "result": "credentials_missing",
            "http_status": None,
            "auth_mode": auth_mode,
            "detail": "Oracle credentials are not configured for the selected authentication mode.",
        }

    endpoint = f"{settings.oracle_base_url.rstrip('/')}/hcmRestApi/resources/11.13.18.05/timeEventRequests/describe"
    headers = {
        "Accept": "application/json",
        "REST-Framework-Version": settings.oracle_rest_framework_version,
    }
    auth = None
    if auth_mode == "basic":
        auth = httpx.BasicAuth(credentials["username"], credentials["password"])
    elif auth_mode == "bearer":
        headers["Authorization"] = f"Bearer {credentials['bearer_token']}"
    else:
        return {
            "credentials_configured": False,
            "validated": False,
            "result": "unsupported_auth_mode",
            "http_status": None,
            "auth_mode": auth_mode,
            "detail": "Oracle authentication mode is unsupported for validation.",
        }

    started = monotonic()
    try:
        # httpx trusts the runtime corporate proxy variables by default. Stream and
        # close without consuming Oracle's response body, which may contain metadata.
        with httpx.Client(timeout=settings.oracle_timeout_seconds, follow_redirects=False, trust_env=True) as client:
            with client.stream("GET", endpoint, headers=headers, auth=auth) as response:
                http_status = response.status_code
        duration_ms = int((monotonic() - started) * 1000)
        if http_status == 407:
            result = "proxy_error"
            detail = "The corporate proxy rejected the Oracle HTTPS request (HTTP 407)."
            validated = False
        elif 200 <= http_status < 300:
            result = "authenticated"
            detail = "Oracle accepted the configured credentials and authorized access to the read-only metadata endpoint."
            validated = True
        elif http_status == 401:
            result = "authentication_rejected"
            detail = "Oracle rejected the configured credentials (HTTP 401)."
            validated = False
        elif http_status == 403:
            result = "insufficient_privilege"
            detail = "Oracle authenticated the request but denied access to the metadata endpoint (HTTP 403)."
            validated = False
        elif 500 <= http_status <= 599:
            result = "oracle_error"
            detail = f"Oracle returned a server error (HTTP {http_status})."
            validated = False
        else:
            result = "http_error"
            detail = f"Oracle metadata validation returned HTTP {http_status}."
            validated = False
        return {
            "credentials_configured": True,
            "validated": validated,
            "result": result,
            "http_status": http_status,
            "auth_mode": auth_mode,
            "duration_ms": duration_ms,
            "detail": detail,
        }
    except httpx.ProxyError:
        result, detail = "proxy_error", "The corporate proxy could not establish the Oracle HTTPS connection."
    except httpx.TimeoutException as exc:
        if isinstance(exc, httpx.ConnectTimeout):
            detail = "Timed out while connecting to Oracle through the configured network path."
        elif isinstance(exc, httpx.ReadTimeout):
            detail = "Oracle did not respond before the configured timeout."
        else:
            detail = "Oracle authentication validation timed out."
        result = "timeout"
    except httpx.ConnectError as exc:
        causes = [exc]
        cause = exc.__cause__
        while cause is not None and cause not in causes:
            causes.append(cause)
            cause = cause.__cause__
        if any(isinstance(cause, ssl.SSLError) for cause in causes):
            result, detail = "tls_error", "TLS negotiation or certificate validation failed for the Oracle HTTPS connection."
        else:
            result, detail = "connectivity_error", "Could not connect to the Oracle host through the configured network path."
    except httpx.HTTPError:
        result, detail = "http_error", "The Oracle metadata request failed at the HTTP transport layer."

    return {
        "credentials_configured": True,
        "validated": False,
        "result": result,
        "http_status": None,
        "auth_mode": auth_mode,
        "duration_ms": int((monotonic() - started) * 1000),
        "detail": detail,
    }


@router.post("/integration-connection-test")
def integration_connection_test():
    """Check HTTPS transport only; never submits or reads time events."""
    try:
        response = httpx.get(settings.oracle_base_url, timeout=settings.oracle_timeout_seconds, follow_redirects=False)
        auth_required = response.status_code in {401, 403}
        return {
            "reachable": True,
            "tls": settings.oracle_base_url.lower().startswith("https://"),
            "http_status": response.status_code,
            "authentication_required": auth_required,
            "authentication_validated": False,
            "detail": (f"Oracle host is reachable, but returned HTTP {response.status_code} (authentication/authorization required)." if auth_required else "Oracle host transport is reachable. This check does not validate credentials."),
        }
    except httpx.HTTPError as exc:
        return {
            "reachable": False,
            "tls": settings.oracle_base_url.lower().startswith("https://"),
            "http_status": None,
            "authentication_required": False,
            "authentication_validated": False,
            "detail": f"Oracle host transport check failed ({type(exc).__name__}).",
        }


@router.get("/terminals", response_model=list[TerminalRead])
def list_terminals(db: Session = Depends(get_db)):
    terminals = db.scalars(select(Terminal).where(Terminal.deleted_at.is_(None)).order_by(Terminal.code)).unique().all()
    return [_terminal_read(item) for item in terminals]


@router.post("/terminals", response_model=TerminalRead, status_code=status.HTTP_201_CREATED)
def create_terminal(payload: TerminalCreate, db: Session = Depends(get_db)):
    terminal_code = payload.code or allocate_terminal_code(db)
    if db.scalar(select(Terminal).where(Terminal.code == terminal_code)):
        raise HTTPException(status_code=409, detail="Terminal code already exists")
    device_id = payload.external_device_id
    if payload.perimeter_only:
        device_id = device_id or (terminal_code if len(terminal_code) <= 40 else "GATE-" + uuid4().hex)
    if not device_id:
        raise HTTPException(422, "Oracle device ID is required for a cell terminal")
    check_device_id(db, device_id)
    actions = [] if payload.perimeter_only else resolve_actions(db, payload.action_codes)
    if payload.active:
        validate_actions(actions, terminal_code, "PERIMETER_BOTH" if payload.perimeter_only else "CELL")
    leaf = None if payload.perimeter_only else _resolve_structure(db, payload.project_line_id, payload.workshop_id, payload.subworkshop_id, required=True)
    terminal = Terminal(
        project_line_id=leaf.id if leaf else None,
        code=terminal_code,
        name=payload.name,
        external_device_id=device_id,
        terminal_role="PERIMETER_BOTH" if payload.perimeter_only else "CELL",
        identification_mode=payload.identification_mode.value,
        exit_menu_timeout_seconds=payload.exit_menu_timeout_seconds if payload.exit_menu_timeout_seconds is not None else 5,
        reporter_id_type=settings.oracle_person_reporter_id_type,
        oracle_attributes={} if payload.perimeter_only else payload.oracle_attributes,
        active=payload.active,
        actions=actions,
    )
    activation_token = issue_activation_token(terminal)
    db.add(terminal)
    _commit_terminal_settings(db, terminal, "DISABLED" if terminal.terminal_role != "CELL" else payload.exit_policy_mode)
    db.refresh(terminal)
    return _terminal_read(terminal, activation_token)


@router.post("/terminals/{terminal_code}/clone", response_model=TerminalRead, status_code=status.HTTP_201_CREATED)
def clone_terminal_configuration(terminal_code: str, db: Session = Depends(get_db)):
    return _terminal_read(clone_terminal(db, terminal_code))


@router.put("/terminals/{terminal_code}", response_model=TerminalRead)
def update_terminal(terminal_code: str, payload: TerminalSettings, db: Session = Depends(get_db)):
    terminal = db.scalar(select(Terminal).where(Terminal.code == terminal_code, Terminal.deleted_at.is_(None)).with_for_update())
    if terminal is None:
        raise HTTPException(404, "Terminal not found")
    perimeter = payload.perimeter_only if payload.perimeter_only is not None else terminal.terminal_role != "CELL"
    role = (terminal.terminal_role if terminal.terminal_role != "CELL" else "PERIMETER_BOTH") if perimeter else "CELL"
    device_id = payload.external_device_id or (terminal.external_device_id if perimeter else None)
    if not device_id:
        raise HTTPException(422, "Oracle device ID is required for a cell terminal")
    check_device_id(db, device_id, terminal)
    actions = [] if perimeter else resolve_actions(db, payload.action_codes)
    if payload.active:
        validate_actions(actions, terminal.code, role)
    leaf = None if perimeter else _resolve_structure(db, payload.project_line_id, payload.workshop_id, payload.subworkshop_id, required=terminal.terminal_role != "CELL")
    terminal.project_line_id = None if perimeter else (leaf.id if leaf else terminal.project_line_id)
    terminal.terminal_role = role
    terminal.name = payload.name
    terminal.external_device_id = device_id
    terminal.identification_mode = payload.identification_mode.value
    if payload.exit_menu_timeout_seconds is not None:
        terminal.exit_menu_timeout_seconds = payload.exit_menu_timeout_seconds
    terminal.reporter_id_type = settings.oracle_person_reporter_id_type
    terminal.oracle_attributes = {} if perimeter else payload.oracle_attributes
    terminal.active = payload.active
    terminal.actions = actions
    _commit_terminal_settings(db, terminal, "DISABLED" if terminal.terminal_role != "CELL" else payload.exit_policy_mode)
    db.refresh(terminal)
    return _terminal_read(terminal)


@router.delete("/terminals/{terminal_code}")
def delete_terminal(terminal_code: str, db: Session = Depends(get_db)):
    terminal = db.scalar(select(Terminal).where(Terminal.code == terminal_code, Terminal.deleted_at.is_(None)).with_for_update())
    if terminal is None:
        raise HTTPException(404, "Terminal not found")
    terminal.active = False
    terminal.deleted_at = datetime.now(timezone.utc)
    terminal.activation_token_hash = None
    terminal.session_token_hash = None
    # Keep approved requests for audit; polling checks the removed terminal.
    for pairing in db.scalars(select(TerminalPairingRequest).where(
        TerminalPairingRequest.terminal_id == terminal.id,
        TerminalPairingRequest.status == "APPROVED",
    )):
        pairing.status = "CANCELLED"
    commit_configuration(db)
    return {"detail": f"Terminal {terminal_code} removed"}


@router.post("/terminals/{terminal_code}/provision", response_model=TerminalProvisioningRead)
def provision_terminal(terminal_code: str, db: Session = Depends(get_db)):
    terminal = db.scalar(select(Terminal).where(Terminal.code == terminal_code, Terminal.deleted_at.is_(None)).with_for_update())
    if terminal is None:
        raise HTTPException(404, "Terminal not found")
    token = issue_activation_token(terminal)
    commit_configuration(db)
    return TerminalProvisioningRead(code=terminal.code, activation_token=token)


@router.post("/terminals/{terminal_code}/pair", response_model=TerminalRead)
def pair_terminal_browser(terminal_code: str, payload: TerminalPairingApproval, db: Session = Depends(get_db)):
    terminal = db.scalar(select(Terminal).where(Terminal.code == terminal_code, Terminal.deleted_at.is_(None)).with_for_update())
    if terminal is None:
        raise HTTPException(404, "Terminal not found")
    approve_pairing_request(db, terminal, payload.pairing_code)
    db.refresh(terminal)
    return _terminal_read(terminal)


@router.put("/terminals/{terminal_code}/actions", response_model=TerminalRead)
def update_terminal_actions(terminal_code: str, payload: TerminalActionsUpdate, db: Session = Depends(get_db)):
    terminal = db.scalar(select(Terminal).where(Terminal.code == terminal_code, Terminal.deleted_at.is_(None)))
    if terminal is None:
        raise HTTPException(status_code=404, detail="Terminal not found")
    actions = resolve_actions(db, payload.action_codes)
    if terminal.active:
        validate_actions(actions, terminal.code, terminal.terminal_role)
    terminal.actions = list(actions)
    commit_configuration(db)
    db.refresh(terminal)
    return _terminal_read(terminal)


@router.get("/actions", response_model=list[ActionRead])
def list_actions(db: Session = Depends(get_db)):
    actions = db.scalars(select(Action).order_by(Action.display_order, Action.code)).unique().all()
    return [_action_read(item) for item in actions]


@router.post("/actions", response_model=ActionRead, status_code=status.HTTP_201_CREATED)
def create_action(payload: ActionCreate, db: Session = Depends(get_db)):
    if db.scalar(select(Action).where(Action.code == payload.code)):
        raise HTTPException(status_code=409, detail="Action code already exists")
    check_supplier_event(db, payload.supplier_device_event)
    oracle_supplier_event = payload.oracle_supplier_event or (
        "HUT_TCD_SUPP1_IN_2" if payload.state_effect.value == "ENTER" else "HUT_TCD_SUPP1_OUT_2"
    )
    parent = resolve_parent_action(db, payload.parent_action_code)
    action = Action(
        code=payload.code,
        label=payload.label,
        supplier_device_event=payload.supplier_device_event,
        oracle_supplier_event=oracle_supplier_event,
        state_effect=payload.state_effect.value,
        oracle_payroll_time_type=payload.oracle_payroll_time_type,
        oracle_attributes=payload.oracle_attributes,
        display_order=payload.display_order,
        requires_subaction=payload.requires_subaction,
        visual_key=payload.visual_key,
        show_on_terminal=payload.show_on_terminal,
        parent_action=parent,
        active=payload.active,
    )
    validate_action_hierarchy(action, parent)
    from app.services.configuration_service import validate_supplier_event_direction
    validate_supplier_event_direction(oracle_supplier_event, payload.state_effect.value)
    db.add(action)
    commit_configuration(db)
    db.refresh(action)
    return _action_read(action)


@router.put("/actions/{action_code}", response_model=ActionRead)
def update_action(action_code: str, payload: ActionSettings, db: Session = Depends(get_db)):
    action = db.scalar(select(Action).where(Action.code == action_code))
    if action is None:
        raise HTTPException(404, "Action not found")
    check_supplier_event(db, payload.supplier_device_event, action)
    oracle_supplier_event = payload.oracle_supplier_event or action.oracle_supplier_event
    parent = resolve_parent_action(db, payload.parent_action_code, action)
    action.label = payload.label
    action.supplier_device_event = payload.supplier_device_event
    action.oracle_supplier_event = oracle_supplier_event
    action.state_effect = payload.state_effect.value
    action.oracle_payroll_time_type = payload.oracle_payroll_time_type
    action.oracle_attributes = payload.oracle_attributes
    action.display_order = payload.display_order
    action.requires_subaction = payload.requires_subaction
    action.visual_key = payload.visual_key
    action.show_on_terminal = payload.show_on_terminal
    action.parent_action = parent
    action.active = payload.active
    try:
        validate_action_hierarchy(action, parent)
        from app.services.configuration_service import validate_supplier_event_direction
        validate_supplier_event_direction(oracle_supplier_event, payload.state_effect.value)
        affected = {terminal.id: terminal for terminal in action.terminals}
        if parent:
            affected.update({terminal.id: terminal for terminal in parent.terminals})
        for child in action.subactions:
            affected.update({terminal.id: terminal for terminal in child.terminals})
        for terminal in affected.values():
            if terminal.active:
                validate_actions(terminal.actions, terminal.code, terminal.terminal_role)
    except HTTPException:
        db.rollback()
        raise
    commit_configuration(db)
    db.refresh(action)
    return _action_read(action)


@router.get("/events", response_model=list[EventRead])
def list_events(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    events = db.scalars(select(TimeEvent).order_by(TimeEvent.created_at.desc()).limit(limit)).all()
    return [EventRead(**{field: getattr(item, field) for field in EventRead.model_fields}) for item in events]


@router.post("/events/{event_id}/retry", response_model=EventRead)
def retry_event(event_id: str, db: Session = Depends(get_db)):
    event = db.get(TimeEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.delivery_status == DeliveryStatus.UNKNOWN.value:
        raise HTTPException(status_code=409, detail="UNKNOWN delivery requires reconciliation before any resend")
    if event.delivery_status == DeliveryStatus.REJECTED.value:
        raise HTTPException(status_code=409, detail="REJECTED delivery cannot be replayed blindly; correct the mapping or source data first")
    if event.delivery_status == DeliveryStatus.SENT.value:
        raise HTTPException(status_code=409, detail="A sent event cannot be replayed")
    if event.delivery_status == DeliveryStatus.SENDING.value:
        raise HTTPException(status_code=409, detail="An event currently being sent cannot be replayed")
    if event.delivery_status == DeliveryStatus.PENDING.value:
        raise HTTPException(status_code=409, detail="This event is already queued for delivery")
    event.delivery_status = DeliveryStatus.PENDING.value
    event.next_attempt_at = None
    db.commit()
    db.refresh(event)
    return EventRead(**{field: getattr(event, field) for field in EventRead.model_fields})
