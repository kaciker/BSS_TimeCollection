import pytest

from app.main import app


class LocalTestAuthenticationProvider:
    @property
    def configured(self):
        return True

    def authenticate(self, request):
        return "test-admin"

    def is_authentication_endpoint(self, request):
        return False


@pytest.fixture(autouse=True)
def provide_admin_authentication_for_application_tests():
    previous = getattr(app.state, "admin_authentication_provider", None)
    app.state.admin_authentication_provider = LocalTestAuthenticationProvider()
    yield
    app.state.admin_authentication_provider = previous
