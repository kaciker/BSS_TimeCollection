from copy import deepcopy

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.terminal import Terminal
from app.services.configuration_service import commit_configuration, validate_actions


def clone_terminal(db: Session, terminal_code: str) -> Terminal:
    # Serialize clones of the same source, including suffix allocation.
    source = db.scalar(select(Terminal).where(Terminal.code == terminal_code).with_for_update())
    if source is None:
        raise HTTPException(404, "Terminal not found")
    if source.active:
        validate_actions(source.actions, source.code)

    index = 1
    while True:
        suffix = f"-{index}"
        code = source.code[:64 - len(suffix)] + suffix
        device_id = source.external_device_id[:128 - len(suffix)] + suffix
        occupied = db.scalar(select(Terminal.id).where(or_(
            Terminal.code == code, Terminal.external_device_id == device_id,
        )).limit(1))
        if occupied is None:
            break
        index += 1

    name_suffix = f" (copy {index})"
    clone = Terminal(
        code=code,
        name=source.name[:160 - len(name_suffix)] + name_suffix,
        external_device_id=device_id,
        identification_mode=source.identification_mode,
        reporter_id_type=source.reporter_id_type,
        oracle_attributes=deepcopy(source.oracle_attributes or {}),
        active=source.active,
        actions=list(source.actions),
    )
    # Browser identity, tokens, diagnostics and event history are never copied.
    db.add(clone)
    commit_configuration(db)
    db.refresh(clone)
    return clone
