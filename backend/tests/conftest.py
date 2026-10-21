import pytest
from fastapi import Request

from app.main import app


class TestAdminAuthProvider:
    @property
    def configured(self) -> bool:
        return True

    def authenticate(self, request: Request) -> str | None:
        return "test-admin"


@pytest.fixture(autouse=True)
def configured_test_admin_provider():
    previous = getattr(app.state, "admin_auth_provider", None)
    previous_test_mode = getattr(app.state, "test_mode", None)
    app.state.test_mode = True
    app.state.admin_auth_provider = TestAdminAuthProvider()
    try:
        yield
    finally:
        if previous is None:
            delattr(app.state, "admin_auth_provider")
        else:
            app.state.admin_auth_provider = previous
        if previous_test_mode is None:
            delattr(app.state, "test_mode")
        else:
            app.state.test_mode = previous_test_mode
