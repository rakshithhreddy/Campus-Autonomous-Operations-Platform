"""
Policy Studio routes — configurable approval policy engine (Item 6).

Admins can create/update/delete per-tenant rules that govern:
- Risk classification (keywords -> risk level)
- Approval requirements (min_approvals, required_roles)
- Auto-approve thresholds
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..core.auth import Principal, get_current_principal, require_role
from ..core.governance_store import get_governance_store
from ..core.policy_engine import PolicyRule


router = APIRouter(prefix="/api/policies", tags=["policies"])


class PolicyRuleRequest(BaseModel):
    rule_id: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=200)
    risk_level: str = Field(..., pattern="^(low|medium|high|critical)$")
    keywords: List[str] = Field(default_factory=list)
    required_roles: List[str] = Field(default_factory=list)
    min_approvals: int = Field(default=1, ge=0, le=10)
    active: bool = True
    version: str = "v1"
    metadata: Dict[str, Any] = Field(default_factory=dict)


@router.get("")
async def list_rules(principal: Principal = Depends(get_current_principal)):
    """List all active policy rules (tenant-scoped + global defaults)."""
    require_role(principal, ["admin", "operator", "reviewer", "auditor"])
    store = get_governance_store()
    all_rules = store.list_policy_rules()
    tenant_rules = [
        r for r in all_rules
        if r.get("metadata", {}).get("tenant_id") in (principal.tenant_id, None, "")
    ]
    return {"rules": tenant_rules, "count": len(tenant_rules)}


@router.post("")
async def create_rule(request: PolicyRuleRequest, principal: Principal = Depends(get_current_principal)):
    """Item 6: Create a new tenant-scoped policy rule. Admin only."""
    require_role(principal, ["admin"])
    store = get_governance_store()
    rule_id = request.rule_id or f"rule_{uuid.uuid4().hex[:8]}"
    rule = PolicyRule(
        rule_id=rule_id,
        name=request.name,
        risk_level=request.risk_level,
        keywords=request.keywords,
        required_roles=request.required_roles,
        min_approvals=request.min_approvals,
        active=request.active,
        version=request.version,
        metadata={**request.metadata, "tenant_id": principal.tenant_id, "created_by": principal.user_id},
    )
    store.upsert_policy_rule(rule)
    return rule.to_dict()


@router.put("/{rule_id}")
async def update_rule(rule_id: str, request: PolicyRuleRequest, principal: Principal = Depends(get_current_principal)):
    """Update an existing policy rule. Admin only."""
    require_role(principal, ["admin"])
    store = get_governance_store()
    existing = next((r for r in store.policy_engine.rules if r.rule_id == rule_id), None)
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found")
    if existing.metadata.get("tenant_id") not in (principal.tenant_id, None, ""):
        raise HTTPException(status_code=403, detail="Cannot modify another tenant's rule")
    rule = PolicyRule(
        rule_id=rule_id,
        name=request.name,
        risk_level=request.risk_level,
        keywords=request.keywords,
        required_roles=request.required_roles,
        min_approvals=request.min_approvals,
        active=request.active,
        version=request.version,
        metadata={**request.metadata, "tenant_id": principal.tenant_id, "updated_by": principal.user_id},
    )
    store.upsert_policy_rule(rule)
    return rule.to_dict()


@router.put("/{rule_id}/activate")
async def activate_rule(rule_id: str, active: bool = True, principal: Principal = Depends(get_current_principal)):
    """Toggle a rule active state. Admin only."""
    require_role(principal, ["admin"])
    store = get_governance_store()
    for rule in store.policy_engine.rules:
        if rule.rule_id == rule_id:
            rule.active = active
            store.upsert_policy_rule(rule)
            return rule.to_dict()
    raise HTTPException(status_code=404, detail="Rule not found")


@router.delete("/{rule_id}")
async def delete_rule(rule_id: str, principal: Principal = Depends(get_current_principal)):
    """Deactivate a tenant rule (soft delete). Admin only."""
    require_role(principal, ["admin"])
    store = get_governance_store()
    for rule in store.policy_engine.rules:
        if rule.rule_id == rule_id:
            if rule.metadata.get("tenant_id") not in (principal.tenant_id, None, ""):
                raise HTTPException(status_code=403, detail="Cannot delete another tenant's rule")
            rule.active = False
            store.upsert_policy_rule(rule)
            return {"status": "deactivated", "rule_id": rule_id}
    raise HTTPException(status_code=404, detail="Rule not found")


@router.post("/evaluate")
async def evaluate_step(request: Dict[str, Any], principal: Principal = Depends(get_current_principal)):
    """Item 6: Evaluate what policy decision a step would get (dry-run)."""
    require_role(principal, ["admin", "operator"])
    from ..core.mission_state import MissionRecord, MissionStep
    store = get_governance_store()
    step = MissionStep(
        id="preview",
        title=str(request.get("title", "")),
        action_type=str(request.get("action_type", "")),
        risk_level=str(request.get("risk_level", "low")),
        requires_approval=bool(request.get("requires_approval", False)),
    )
    dummy_mission = MissionRecord(
        mission_id="preview",
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        title="Preview",
    )
    decision = store.policy_engine.evaluate_step(dummy_mission, step)
    return {
        "step_title": step.title,
        "evaluated_risk": decision.risk_level,
        "requires_approval": decision.requires_approval,
        "min_approvals": decision.min_approvals,
        "matched_rule_id": decision.policy_rule_id,
        "required_roles": decision.required_roles,
    }


@router.get("/config")
async def get_policy_config(principal: Principal = Depends(get_current_principal)):
    """Item 6: Get the current tenant policy configuration."""
    require_role(principal, ["admin", "reviewer", "auditor"])
    return {
        "tenant_id": principal.tenant_id,
        "auto_approve_below_risk": "low",
        "require_multi_approval_above_risk": "high",
        "default_min_approvals": 1,
        "critical_min_approvals": 2,
    }