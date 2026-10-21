from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.admin_auth import authenticated_admin, router as admin_auth_router
from app.core.config import settings
from app.routers import admin, database_admin, health, monitoring, terminal, policies, structure, perimeter


app = FastAPI(
    title="BSS Time Collection",
    version="0.1.0",
    description="External Time Collection Device event collector for Oracle HCM Time and Labor.",
)


@app.middleware("http")
async def temporary_admin_auth(request: Request, call_next):
    path = request.url.path
    auth_path = path.startswith("/api/v1/admin/auth")
    admin_api = path.startswith("/api/v1/admin")
    if settings.admin_auth_enabled and admin_api and not auth_path:
        if authenticated_admin(request) is None:
            return JSONResponse(status_code=401, content={"detail": "Admin authentication required."})
    return await call_next(request)


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
        "authentication": "temporary-admin-session" if settings.admin_auth_enabled else "disabled",
        "scope": "external-time-collection-device",
    }
