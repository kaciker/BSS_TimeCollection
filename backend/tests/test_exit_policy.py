from unittest.mock import MagicMock
from fastapi import HTTPException
from app.services.exit_policy import MODES, check_exit_policy, get_mode


def test_available_modes():
    assert MODES == {"DISABLED", "SAME_TERMINAL", "SAME_WORK_CELL"}


def test_disabled_policy_allows_exit(monkeypatch):
    monkeypatch.setattr("app.services.exit_policy.get_mode", lambda db, terminal_id: "DISABLED")
    terminal = MagicMock(id=1)
    check_exit_policy(MagicMock(), terminal, "123")


def test_missing_entry_is_rejected(monkeypatch):
    monkeypatch.setattr("app.services.exit_policy.get_mode", lambda db, terminal_id: "SAME_TERMINAL")
    db = MagicMock()
    db.scalar.return_value = None
    try:
        check_exit_policy(db, MagicMock(id=1), "123")
    except HTTPException as error:
        assert error.status_code == 409
    else:
        raise AssertionError("Expected missing entry to be rejected")
