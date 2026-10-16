from copy import deepcopy

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.terminal import Terminal
from app.services.configuration_service import commit_configuration, validate_actions
from app.services.terminal_code_service import allocate_terminal_code


def _allocate_cloned_device_id(db: Session, source: Terminal) -> tuple[str, int]:
    index = 1
    while True:
        suffix = f"-{index}"
        device_id = source.external_device_id[:128 - len(suffix)] + suffix
        occupied = db.scalar(select(Terminal.id).where(Terminal.external_device_id == device_id).limit(1))
        if occupied is None:
            return device_id, index
        index += 1


def clone_terminal(db: Session, terminal_code: str) -> Terminal:
    # Serialize clones of the same source and keep source settings stable while copying.
    source = db.scalar(select(Terminal).where(Terminal.code == terminal_code, Terminal.deleted_at.is_(None)).with_for_update())
    if source is None:
        raise HTTPException(404, "Terminal not found")
    if source.active:
        validate_actions(source.actions, source.code)

    code = allocate_terminal_code(db)
    device_id, copy_index = _allocate_cloned_device_id(db, source)
    name_suffix = f" (copy {copy_index})"
    clone = Terminal(
        code=code,
        name=source.name[:160 - len(name_suffix)] + name_suffix,
        external_device_id=device_id,
        identification_mode=source.identification_mode,
        reporter_id_type=settings.oracle_reporter_id_type,
        oracle_attributes=deepcopy(source.oracle_attributes or {}),
        project_line_id=source.project_line_id,
        active=source.active,
        actions=list(source.actions),
    )
    # Browser identity, tokens, diagnostics and event history are never copied.
    db.add(clone)
    commit_configuration(db)
    db.refresh(clone)
    return clone
