from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette import status
from app.core.admin_auth import AdminAuthProvider
from app.routers import admin, database_admin, health, monitoring, terminal, policies, structure, perimeter


app = FastAPI(
    title="BSS Time Collection",
    version="0.1.0",
    description="External Time Collection Device event collector for Oracle HCM Time and Labor.",
)


@app.middleware("http")
async def require_admin_authentication(request: Request, call_next):
    if request.url.path == "/api/v1/admin" or request.url.path.startswith("/api/v1/admin/"):
        provider: AdminAuthProvider | None = getattr(request.app.state, "admin_auth_provider", None)
        if provider is None:
            return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                content={"detail": "Admin authentication provider is not configured."})
        try:
            configured = provider.configured
        except Exception:
            configured = False
        if not configured:
            return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                content={"detail": "Admin authentication provider is not configured."})
        try:
            principal = provider.authenticate(request)
        except Exception:
            principal = None
        if not principal:
            return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED,
                                content={"detail": "Admin authentication required."})
        request.state.admin_principal = principal
    return await call_next(request)


app.include_router(health.router)
app.include_router(terminal.router)
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
        "authentication": "terminal-http-only-session; admin-authentication-provider-required",
        "scope": "external-time-collection-device",
    }
