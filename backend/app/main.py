from fastapi import FastAPI
from app.db.session import engine
from app.services.exit_policy import ensure_policy_table

from app.routers import admin, database_admin, health, monitoring, terminal, policies

ensure_policy_table(engine)

app = FastAPI(
    title="BSS Time Collection",
    version="0.1.0",
    description="External Time Collection Device event collector for Oracle HCM Time and Labor.",
)

app.include_router(health.router)
app.include_router(terminal.router)
app.include_router(admin.router)
app.include_router(policies.router)
app.include_router(database_admin.router)
app.include_router(monitoring.router)


@app.get("/api/v1/meta")
def meta():
    return {
        "name": "BSS Time Collection",
        "version": "0.1.0",
        "authentication": "disabled",
        "scope": "external-time-collection-device",
    }
