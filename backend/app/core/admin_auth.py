"""Provider-independent contract used to protect every Admin API route."""

from typing import Protocol, runtime_checkable

from fastapi import Request


@runtime_checkable
class FailClosedAdminAuthProvider(Protocol):
    """Provider contract for authenticating Admin API requests.

    Providers report configuration separately so the enforcement layer can
    return unavailable when auth is not configured and deny invalid requests.
    """

    @property
    def configured(self) -> bool: ...

    def authenticate(self, request: Request) -> str | None: ...


AdminAuthProvider = FailClosedAdminAuthProvider
