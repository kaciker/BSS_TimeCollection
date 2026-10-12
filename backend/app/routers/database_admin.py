from time import perf_counter

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings

router = APIRouter(prefix="/api/v1/admin/database", tags=["admin-database"])


class DatabaseStatusRead(BaseModel):
    backend: str
    host: str | None
    port: int | None
    database: str | None
    username: str | None
    source: str
    connection_test_enabled: bool


class ExternalDatabaseTestRequest(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=512)
    sslmode: str = Field(default="prefer", pattern="^(disable|allow|prefer|require|verify-ca|verify-full)$")


class ExternalDatabaseTestRead(BaseModel):
    success: bool
    backend: str
    host: str
    port: int
    database: str
    latency_ms: int


@router.get("", response_model=DatabaseStatusRead)
def database_status():
    url = make_url(settings.database_url)
    host = url.host
    source = "local-compose" if host == "db" else "external"
    return DatabaseStatusRead(
        backend=url.get_backend_name(),
        host=host,
        port=url.port,
        database=url.database,
        username=url.username,
        source=source,
        connection_test_enabled=settings.database_admin_test_enabled,
    )


@router.post("/test", response_model=ExternalDatabaseTestRead)
def test_external_database(payload: ExternalDatabaseTestRequest):
    if not settings.database_admin_test_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="External database connection tests are disabled by server configuration",
        )

    url = URL.create(
        "postgresql+psycopg",
        username=payload.username,
        password=payload.password,
        host=payload.host,
        port=payload.port,
        database=payload.database,
        query={"sslmode": payload.sslmode},
    )
    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        connect_args={"connect_timeout": 5},
    )
    started = perf_counter()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not connect to the external PostgreSQL database with the supplied settings",
        ) from exc
    finally:
        engine.dispose()

    return ExternalDatabaseTestRead(
        success=True,
        backend="postgresql",
        host=payload.host,
        port=payload.port,
        database=payload.database,
        latency_ms=max(1, round((perf_counter() - started) * 1000)),
    )
