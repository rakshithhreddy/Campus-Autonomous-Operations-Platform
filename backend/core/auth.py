"""
Authentication and request principal resolution.

Provides a single dependency that binds requests to an authenticated principal.
In development/testing, a controlled local bypass is supported to avoid blocking
local iteration. In non-development environments, JWT is mandatory.
"""

from dataclasses import dataclass
import os
from typing import List, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt


@dataclass
class Principal:
    user_id: str
    tenant_id: str
    roles: List[str]


_bearer = HTTPBearer(auto_error=False)


def _is_dev_like_env() -> bool:
    env = (os.getenv("APP_ENV") or os.getenv("ENV") or "development").strip().lower()
    return env in {"development", "dev", "testing", "test", "local"}


def _get_jwt_secret() -> str:
    secret = (os.getenv("SECRET_KEY") or "").strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Server auth is not configured", "code": "auth_not_configured"},
        )
    return secret


def _decode_principal_from_token(token: str) -> Principal:
    secret = _get_jwt_secret()
    algorithms = [os.getenv("JWT_ALGORITHM", "HS256")]

    try:
        claims = jwt.decode(token, secret, algorithms=algorithms)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid access token", "code": "invalid_token"},
        ) from exc

    user_id = str(claims.get("sub") or claims.get("user_id") or "").strip()
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Token missing subject", "code": "invalid_token_claims"},
        )

    tenant_id = str(claims.get("tenant_id") or "default").strip()
    raw_roles: Optional[object] = claims.get("roles")
    if isinstance(raw_roles, list):
        roles = [str(r).strip() for r in raw_roles if str(r).strip()]
    elif isinstance(raw_roles, str) and raw_roles.strip():
        roles = [r.strip() for r in raw_roles.split(",") if r.strip()]
    else:
        roles = ["user"]

    return Principal(user_id=user_id, tenant_id=tenant_id, roles=roles)


def _dev_principal_from_headers(request: Request) -> Principal:
    user_id = (request.headers.get("X-Dev-User-Id") or "dev-user").strip()
    tenant_id = (request.headers.get("X-Dev-Tenant-Id") or "dev-tenant").strip()
    raw_roles = (request.headers.get("X-Dev-Roles") or "admin,user").strip()
    roles = [r.strip() for r in raw_roles.split(",") if r.strip()] or ["user"]
    return Principal(user_id=user_id, tenant_id=tenant_id, roles=roles)


async def get_current_principal(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Principal:
    """
    Resolve authenticated principal for the request.

    Behavior:
    - Non-dev environments: requires valid bearer JWT.
    - Dev/testing environments: supports explicit dev bypass if no token provided.
    """

    if credentials and credentials.scheme.lower() == "bearer" and credentials.credentials:
        return _decode_principal_from_token(credentials.credentials)

    if _is_dev_like_env():
        return _dev_principal_from_headers(request)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": "Authentication required", "code": "auth_required"},
    )


def require_role(principal: Principal, allowed_roles: List[str]) -> None:
    """Simple role gate helper for route-level authorization checks."""
    allowed = set(allowed_roles)
    if not any(role in allowed for role in principal.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Forbidden", "code": "insufficient_permissions"},
        )
