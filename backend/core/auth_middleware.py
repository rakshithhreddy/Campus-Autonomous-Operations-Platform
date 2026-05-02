"""
AuthMiddleware — enforces authentication on every business endpoint.

Public paths (health, docs, webhooks) are explicitly allowlisted.
All other paths require a valid JWT or (in dev only) dev-header bypass.
The resolved principal is attached to request.state.principal so route
handlers can access it without re-decoding the token.
"""

from __future__ import annotations

import os
from typing import Set

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .auth import _decode_principal_from_token, _dev_principal_from_headers, _is_dev_like_env

# Paths that never require authentication
_DEFAULT_PUBLIC_PATHS: Set[str] = {
    "/",
    "/api/health",
    "/api/health/ready",
    "/api/health/metrics",
    "/api/docs",
    "/api/redoc",
    "/openapi.json",
    "/api/status",
    "/api/metrics",
    # Webhook paths authenticated via their own signature checks
    "/webhook/telegram",
    "/webhook/whatsapp",
    "/webhook/twilio",
    "/webhook/voice",
}

_PUBLIC_PREFIXES = (
    "/api/health",
    "/api/docs",
    "/api/redoc",
    "/openapi",
    "/webhook/",
    "/static/",
)


def _is_public(path: str, public_paths: Set[str]) -> bool:
    if path in public_paths:
        return True
    return any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES)


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that validates bearer JWT on every non-public path.

    On success: attaches Principal to request.state.principal.
    On failure in production: returns 401 JSON immediately.
    On failure in dev: falls back to dev-header principal.
    """

    def __init__(self, app, public_paths: Set[str] | None = None):
        super().__init__(app)
        self._public_paths: Set[str] = _DEFAULT_PUBLIC_PATHS | (public_paths or set())

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Always allow OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Skip auth for explicitly public paths
        if _is_public(path, self._public_paths):
            return await call_next(request)

        # Attempt JWT extraction
        auth_header = request.headers.get("Authorization", "")
        token: str | None = None
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()

        if token:
            try:
                principal = _decode_principal_from_token(token)
                request.state.principal = principal
                return await call_next(request)
            except Exception:
                # Invalid token — fall through to dev bypass or 401
                pass

        # Dev-only bypass
        if _is_dev_like_env():
            request.state.principal = _dev_principal_from_headers(request)
            return await call_next(request)

        # Production: reject unauthenticated request
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Authentication required", "code": "auth_required"},
            headers={"WWW-Authenticate": "Bearer"},
        )
