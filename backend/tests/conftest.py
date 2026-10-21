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
    app.state.admin_auth_provider = TestAdminAuthProvider()
    try:
        yield
    finally:
        if previous is None:
            delattr(app.state, "admin_auth_provider")
        else:
            app.state.admin_auth_provider = previous
