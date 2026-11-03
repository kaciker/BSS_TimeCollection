import pytest
from sqlalchemy import create_engine, event as sqlalchemy_event, insert
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.base import Base
from app.models.oracle_catalogue import OracleCell, OracleMachine, OraclePayrollTimeType, OracleWorkArea


@sqlalchemy_event.listens_for(OracleWorkArea.__table__, "after_create")
def _seed_test_work_areas(target, connection, **kwargs):
    connection.execute(insert(target), [{"code":"439","description":"Acabado TP","active":True}])


@sqlalchemy_event.listens_for(OracleMachine.__table__, "after_create")
def _seed_test_machines(target, connection, **kwargs):
    connection.execute(insert(target), [
        {"code":"4391","description":"T439.1","work_area_code":"439","active":True},
        {"code":"4392","description":"T439.2","work_area_code":"439","active":True},
        {"code":"4393","description":"T439.3 Recambios","work_area_code":"439","active":True},
    ])


@sqlalchemy_event.listens_for(OracleCell.__table__, "after_create")
def _seed_test_cells(target, connection, **kwargs):
    connection.execute(insert(target), [
        {"code":"54Q","description":"G.V. D34","machine_code":"4391","active":True},
        {"code":"54T","description":"G.V. P24","machine_code":"4391","active":True},
        {"code":"54A","description":"Lam y G.V. B75","machine_code":"4393","active":True},
    ])


@sqlalchemy_event.listens_for(OraclePayrollTimeType.__table__, "after_create")
def _seed_test_payroll(target, connection, **kwargs):
    connection.execute(insert(target), [{"code":code,"active":True} for code in (
        "Public Holiday ES", "Workshop Entry ES", "Project Entry ES", "Non-productive time ES", "Break ES",
    )])


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


@pytest.fixture(autouse=True)
def use_persistent_catalogue_test_database(monkeypatch):
    """Direct OracleClient unit tests use a real DB-backed catalogue too."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread":False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    import app.integrations.oracle.client as oracle_client
    import app.db.session as db_session
    monkeypatch.setattr(oracle_client, "SessionLocal", factory)
    monkeypatch.setattr(db_session, "SessionLocal", factory)
    yield
    engine.dispose()
