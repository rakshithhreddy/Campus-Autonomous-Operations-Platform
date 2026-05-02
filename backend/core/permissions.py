"""
Role-based access control: permission matrix and dependency factory.
"""

from __future__ import annotations

from typing import List

from fastapi import Depends, HTTPException, status

from .auth import Principal, get_current_principal, require_role

# ---------------------------------------------------------------------------
# Role → endpoint permission matrix
# ---------------------------------------------------------------------------

ENDPOINT_ROLE_MAP: dict[str, List[str]] = {
    # --- Missions ---
    "create_mission":           ["admin", "operator", "user"],
    "list_own_missions":        ["admin", "operator", "user", "reviewer", "auditor"],
    "list_all_missions":        ["admin", "auditor"],
    "view_mission":             ["admin", "operator", "user", "reviewer", "auditor"],
    "transition_mission":       ["admin", "operator"],
    "replan_mission":           ["admin", "operator", "user"],
    # --- Approvals ---
    "approve_mission_step":     ["admin", "manager", "reviewer"],
    "list_approvals":           ["admin", "manager", "reviewer", "auditor"],
    # --- Overrides ---
    "override_step":            ["admin", "reviewer"],
    "list_overrides":           ["admin", "reviewer", "auditor"],
    # --- Evidence ---
    "view_evidence":            ["admin", "auditor", "reviewer", "operator", "user"],
    "store_evidence":           ["admin", "operator", "user"],
    "export_bundle":            ["admin", "auditor"],
    "verify_evidence":          ["admin", "auditor", "reviewer"],
    # --- Policies ---
    "manage_policies":          ["admin"],
    "view_policies":            ["admin", "operator", "reviewer", "auditor"],
    # --- Integrations ---
    "create_integration":       ["admin", "operator"],
    "delete_integration":       ["admin"],
    "view_integrations":        ["admin", "operator", "user", "reviewer"],
    # --- Analytics / Trust ---
    "view_trust":               ["admin", "operator", "reviewer", "auditor"],
    "view_analytics":           ["admin", "auditor"],
    # --- Tasks ---
    "manage_tasks":             ["admin", "operator", "user"],
    # --- Capabilities ---
    "view_capabilities":        ["admin", "operator", "user", "reviewer", "auditor"],
    # --- Learning ---
    "view_learning_stats":      ["admin"],
}


def require_endpoint_role(action: str):
    """
    FastAPI dependency factory. Returns a Depends that:
    1. Resolves the current principal (JWT or dev bypass)
    2. Checks that the principal holds at least one allowed role
    3. Returns the principal for use in the route handler

    Usage:
        @router.get("/foo")
        async def foo(principal: Principal = require_endpoint_role("view_evidence")):
            ...
    """
    allowed = ENDPOINT_ROLE_MAP.get(action)
    if allowed is None:
        raise ValueError(f"Unknown action '{action}' in ENDPOINT_ROLE_MAP")

    async def dependency(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        if not any(role in set(allowed) for role in principal.roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "You do not have permission to perform this action.",
                    "code": "insufficient_permissions",
                    "required_roles": allowed,
                },
            )
        return principal

    return Depends(dependency)
