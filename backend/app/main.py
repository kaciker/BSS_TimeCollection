from fastapi import FastAPI

from app.core.admin_auth import provider as admin_auth_provider, router as admin_auth_router
from app.core.admin_security import install_admin_authentication
from app.routers import admin, database_admin, health, monitoring, terminal, policies, structure, perimeter


app = FastAPI(
    title="BSS Time Collection",
    version="0.1.0",
    description="External Time Collection Device event collector for Oracle HCM Time and Labor.",
)


install_admin_authentication(app, admin_auth_provider)

app.include_router(health.router)
app.include_router(terminal.router)
app.include_router(admin_auth_router)
app.include_router(admin.router)
app.include_router(structure.router)
app.include_router(policies.router)
app.include_router(perimeter.router)
app.include_router(database_admin.router)
app.include_router(monitoring.router)


@app.get("/api/v1/meta")
def meta():
    return {
        "name": "BSS Time Collection",
        "version": "0.1.0",
        "authentication": "temporary-admin-session",
        "scope": "external-time-collection-device",
    }
