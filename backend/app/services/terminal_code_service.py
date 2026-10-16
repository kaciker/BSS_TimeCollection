import re
from hashlib import sha256

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.terminal import Terminal

_CODE_PATTERN = re.compile(r"^T(\d+)$")
_LOCK_KEY = int.from_bytes(sha256(b"bss-timecollection-terminal-code").digest()[:8], "big", signed=True)


def allocate_terminal_code(db: Session) -> str:
    """Allocate a stable application-managed terminal code without reusing retired codes."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _LOCK_KEY})

    highest = 0
    for code in db.scalars(select(Terminal.code)).all():
        match = _CODE_PATTERN.fullmatch(code or "")
        if match:
            highest = max(highest, int(match.group(1)))

    candidate = highest + 1
    while True:
        code = f"T{candidate:04d}"
        if db.scalar(select(Terminal.id).where(Terminal.code == code).limit(1)) is None:
            return code
        candidate += 1
