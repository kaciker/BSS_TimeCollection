"""Provider-independent enforcement contract for administrative API access."""

from typing import Protocol

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse


class AdminAuthenticationProvider(Protocol):
    """Provider reports configuration and validates principals for Admin requests."""

    @property
    def configured(self) -> bool: ...

    def authenticate(self, request: Request) -> str | None: ...

    def is_authentication_endpoint(self, request: Request) -> bool: ...


def require_admin_principal(
    request: Request,
    provider: AdminAuthenticationProvider | None,
) -> str:
    """Fail closed when the provider is absent, unavailable, or rejects access."""
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin authentication provider is not configured.",
        )

    try:
        if not provider.configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Admin authentication provider is not configured.",
            )
        principal = provider.authenticate(request)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin authentication provider is unavailable.",
        )

    if not principal:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal


def enforce_admin_authentication(
    request: Request,
    provider: AdminAuthenticationProvider | None,
) -> None:
    """Protect every Admin path; only a configured provider may open its login route."""
    path = request.url.path
    if path == "/api/v1/admin" or path.startswith("/api/v1/admin/"):
        if provider is not None:
            try:
                if provider.configured and provider.is_authentication_endpoint(request):
                    return
            except Exception:
                pass
        require_admin_principal(request, provider)


def install_admin_authentication(
    app: FastAPI,
    provider: AdminAuthenticationProvider | None = None,
) -> None:
    """Install fail-closed enforcement; deployment code supplies its provider."""
    app.state.admin_authentication_provider = provider

    @app.middleware("http")
    async def admin_authentication_middleware(request: Request, call_next):
        try:
            enforce_admin_authentication(
                request,
                getattr(request.app.state, "admin_authentication_provider", None),
            )
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers,
            )
        return await call_next(request)
