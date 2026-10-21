"""Provider-independent contract for Admin API authentication."""

from typing import Protocol, runtime_checkable

from fastapi import Request


@runtime_checkable
class FailClosedAdminAuthProvider(Protocol):
    @property
    def configured(self) -> bool: ...
    def authenticate(self, request: Request) -> str | None: ...


AdminAuthProvider = FailClosedAdminAuthProvider
