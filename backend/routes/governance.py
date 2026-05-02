"""
Governance API routes for mission creation, approval decisions, and trust summaries.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..core.auth import Principal, get_current_principal, require_role
from ..core.governance_store import ApprovalDecisionRecord, get_governance_store
from ..core.mission_state import MissionState
from ..core.telemetry import get_telemetry
from ..core.workflow_packs import get_workflow_pack, list_workflow_packs


router = APIRouter(prefix="/api/governance", tags=["governance"])


class MissionStepInput(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = ""
    action_type: str = ""
    risk_level: str = "low"
    requires_approval: bool = False
    approver_roles: List[str] = Field(default_factory=list)
    owner_role: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CreateMissionRequest(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = ""
    steps: List[MissionStepInput] = Field(default_factory=list)
    policy_version: str = "v1"


class CreateMissionFromPackRequest(BaseModel):
    pack_id: str = Field(..., min_length=1)
    title: Optional[str] = None
    description: Optional[str] = None
    policy_version: str = "v1"


class ApprovalDecisionRequest(BaseModel):
    step_id: str = Field(..., min_length=1)
    decision: str = Field(..., pattern="^(approve|rejected|reject|request_changes)$")
    reason: str = Field(..., min_length=10)  # Item 8: force meaningful reason


class TransitionRequest(BaseModel):
    next_state: str = Field(..., min_length=1)
    reason: str = Field(default="", min_length=0, max_length=500)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReplanRequest(BaseModel):  # Item 8
    replan_notes: str = Field(..., min_length=10, max_length=1000)


class StepFailureRequest(BaseModel):
    step_id: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    retry_strategy: Optional[str] = None
    fallback_strategy: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ManualOverrideRequest(BaseModel):
    step_id: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    override_action: str = Field(..., min_length=1)
    reviewer_visibility_notes: Optional[str] = None


def _mission_or_404(mission_id: str, tenant_id: Optional[str] = None):
    """Item 5: tenant_id enforced — cross-tenant access returns 404 (not 403, to prevent enumeration)."""
    store = get_governance_store()
    mission = store.get_mission(mission_id, tenant_id=tenant_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission


@router.post("/missions")
async def create_mission(request: CreateMissionRequest, raw_request: Request, principal: Principal = Depends(get_current_principal)):
    store = get_governance_store()
    idempotency_key = (raw_request.headers.get("X-Idempotency-Key") or "").strip() or None
    mission = store.create_mission(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        title=request.title,
        description=request.description,
        steps=[step.model_dump() for step in request.steps],
        policy_version=request.policy_version,
        idempotency_key=idempotency_key,
    )
    get_telemetry().record_event(
        "mission_created_api",
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        mission_id=mission.mission_id,
    )
    return mission.to_dict()


@router.get("/workflow-packs")
async def workflow_packs(principal: Principal = Depends(get_current_principal)):
    return {"packs": list_workflow_packs()}


@router.post("/missions/from-pack")
async def create_mission_from_pack(request: CreateMissionFromPackRequest, raw_request: Request, principal: Principal = Depends(get_current_principal)):
    pack = get_workflow_pack(request.pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Workflow pack not found")

    store = get_governance_store()
    idempotency_key = (raw_request.headers.get("X-Idempotency-Key") or "").strip() or None
    mission = store.create_mission(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        title=(request.title or pack.get("default_title") or pack.get("name") or request.pack_id),
        description=(request.description or pack.get("description") or ""),
        steps=pack.get("steps", []),
        policy_version=request.policy_version,
        idempotency_key=idempotency_key,
    )

    get_telemetry().record_event(
        "mission_created_from_pack",
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        mission_id=mission.mission_id,
        properties={"pack_id": request.pack_id},
    )
    return mission.to_dict()


@router.get("/missions")
async def list_missions(principal: Principal = Depends(get_current_principal)):
    store = get_governance_store()
    # Item 5: tenant_id mandatory
    missions = store.list_missions(principal.user_id, tenant_id=principal.tenant_id)
    return {"missions": [mission.to_dict() for mission in missions], "count": len(missions)}


@router.get("/missions/{mission_id}")
async def get_mission(mission_id: str, principal: Principal = Depends(get_current_principal)):
    # Item 5: tenant_id enforced in lookup
    mission = _mission_or_404(mission_id, tenant_id=principal.tenant_id)
    if mission.user_id != principal.user_id and not ({"admin", "auditor", "reviewer"} & set(principal.roles)):
        raise HTTPException(status_code=403, detail="Forbidden")
    return mission.to_dict()


@router.post("/missions/{mission_id}/transition")
async def transition_mission(mission_id: str, request: TransitionRequest, principal: Principal = Depends(get_current_principal)):
    mission = _mission_or_404(mission_id, tenant_id=principal.tenant_id)
    if mission.user_id != principal.user_id and not ({"admin", "operator"} & set(principal.roles)):
        raise HTTPException(status_code=403, detail="Forbidden")

    store = get_governance_store()
    try:
        event = store.transition_mission(
            mission_id,
            MissionState(request.next_state),
            actor_id=principal.user_id,
            reason=request.reason,
            metadata=request.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"status": "ok", "event": event.to_dict(), "mission": mission.to_dict()}


@router.get("/approvals")
async def list_pending_approvals(principal: Principal = Depends(get_current_principal)):
    store = get_governance_store()
    approvals = store.list_pending_approvals(tenant_id=principal.tenant_id, user_id=principal.user_id)
    return {"approvals": approvals, "count": len(approvals)}


@router.post("/missions/{mission_id}/approval")
async def record_approval(mission_id: str, request: ApprovalDecisionRequest, principal: Principal = Depends(get_current_principal)):
    mission = _mission_or_404(mission_id)
    if mission.tenant_id != principal.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    target_step = next((step for step in mission.steps if step.id == request.step_id), None)
    if not target_step:
        raise HTTPException(status_code=404, detail="Mission step not found")

    if mission.user_id != principal.user_id:
        allowed_roles = set(target_step.approver_roles or [])
        privileged_roles = {"admin", "reviewer", "manager"}
        principal_roles = set(principal.roles)
        if not (principal_roles & allowed_roles or principal_roles & privileged_roles):
            raise HTTPException(status_code=403, detail="Forbidden")

    store = get_governance_store()
    required_approvals = store.required_approvals_for_step(mission, target_step)
    approval = store.record_approval(
        mission_id=mission_id,
        step_id=request.step_id,
        tenant_id=principal.tenant_id,
        user_id=mission.user_id,
        approver_id=principal.user_id,
        approver_roles=principal.roles,
        decision=request.decision,
        reason=request.reason,
        policy_version=mission.policy_version,
    )

    if request.decision in {"approve", "approved"}:
        current_approvals = store.count_step_approvals(mission_id, request.step_id)
        if current_approvals >= required_approvals:
            target_step.state = "approved"
            target_step.approval_decision_id = approval.decision_id
            target_step.updated_at = __import__('datetime').datetime.utcnow().isoformat()
        else:
            target_step.state = "awaiting_more_approvals"
        if all(not step.requires_approval or step.approval_decision_id for step in mission.steps):
            try:
                store.transition_mission(mission_id, MissionState.RUNNING, actor_id=principal.user_id, reason="all approvals recorded")
            except ValueError:
                pass
    else:
        # Item 8: capture rich rejection metadata
        target_step.state = "rejected"
        target_step.metadata["rejection_reason"] = request.reason
        target_step.metadata["rejected_by"] = principal.user_id
        target_step.metadata["rejected_at"] = __import__('datetime').datetime.utcnow().isoformat()
        target_step.updated_at = target_step.metadata["rejected_at"]
        try:
            store.transition_mission(mission_id, MissionState.PLANNED, actor_id=principal.user_id, reason=request.reason)
        except ValueError:
            pass

    return {
        "status": "recorded",
        "approval": approval.to_dict(),
        "mission": mission.to_dict(),
        "required_approvals": required_approvals,
        "current_approvals": store.count_step_approvals(mission_id, request.step_id),
    }


@router.post("/missions/{mission_id}/steps/failure")
async def record_step_failure(mission_id: str, request: StepFailureRequest, principal: Principal = Depends(get_current_principal)):
    mission = _mission_or_404(mission_id)
    if mission.tenant_id != principal.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if mission.user_id != principal.user_id and not ({"admin", "manager", "reviewer"} & set(principal.roles)):
        raise HTTPException(status_code=403, detail="Forbidden")

    target_step = next((step for step in mission.steps if step.id == request.step_id), None)
    if not target_step:
        raise HTTPException(status_code=404, detail="Mission step not found")

    failure_record = get_governance_store().record_step_failure(
        mission_id=mission_id,
        step_id=request.step_id,
        actor_id=principal.user_id,
        reason=request.reason,
        retry_strategy=request.retry_strategy,
        fallback_strategy=request.fallback_strategy,
        metadata=request.metadata,
    )
    return {"status": "recorded", "failure": failure_record}


@router.post("/missions/{mission_id}/override")
async def create_manual_override(mission_id: str, request: ManualOverrideRequest, principal: Principal = Depends(get_current_principal)):
    require_role(principal, ["admin", "reviewer", "manager"])
    mission = _mission_or_404(mission_id, tenant_id=principal.tenant_id)
    if mission.tenant_id != principal.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    target_step = next((step for step in mission.steps if step.id == request.step_id), None)
    if not target_step:
        raise HTTPException(status_code=404, detail="Mission step not found")

    override_record = get_governance_store().record_manual_override(
        mission_id=mission_id,
        step_id=request.step_id,
        tenant_id=principal.tenant_id,
        actor_id=principal.user_id,
        reason=request.reason,
        override_action=request.override_action,
        reviewer_visibility_notes=request.reviewer_visibility_notes,
    )
    return {"status": "recorded", "override": override_record.to_dict()}


@router.get("/missions/{mission_id}/overrides")
async def list_manual_overrides(mission_id: str, principal: Principal = Depends(get_current_principal)):
    require_role(principal, ["admin", "reviewer", "auditor"])
    mission = _mission_or_404(mission_id, tenant_id=principal.tenant_id)
    return {"overrides": get_governance_store().list_manual_overrides(mission_id)}


@router.get("/approvals/{decision_id}")
async def get_approval(decision_id: str, principal: Principal = Depends(get_current_principal)):
    store = get_governance_store()
    for approval in store._approvals.values():
        if approval.decision_id == decision_id:
            if approval.tenant_id != principal.tenant_id:
                raise HTTPException(status_code=403, detail="Forbidden")
            return approval.to_dict()
    raise HTTPException(status_code=404, detail="Approval not found")


@router.get("/trust")
async def trust_summary(principal: Principal = Depends(get_current_principal)):
    store = get_governance_store()
    summary = store.get_trust_summary(tenant_id=principal.tenant_id, user_id=principal.user_id)
    summary["telemetry"] = get_telemetry().summarize(principal.tenant_id)
    return summary


@router.get("/missions/{mission_id}/bundle")
async def mission_bundle(mission_id: str, principal: Principal = Depends(get_current_principal)):
    mission = _mission_or_404(mission_id, tenant_id=principal.tenant_id)
    if mission.user_id != principal.user_id and not ({"admin", "auditor"} & set(principal.roles)):
        raise HTTPException(status_code=403, detail="Forbidden")
    store = get_governance_store()
    return store.export_mission_bundle(mission_id)


# =============================================================================
# Item 8: Re-plan endpoint
# =============================================================================

@router.post("/missions/{mission_id}/replan")
async def replan_mission(
    mission_id: str,
    request: ReplanRequest,
    principal: Principal = Depends(get_current_principal),
):
    """Reset rejected steps and send mission back to approval queue."""
    mission = _mission_or_404(mission_id, tenant_id=principal.tenant_id)
    if mission.user_id != principal.user_id and not ({"admin", "operator"} & set(principal.roles)):
        raise HTTPException(status_code=403, detail="Forbidden")
    if mission.state not in {MissionState.PLANNED, MissionState.WAITING_APPROVAL}:
        raise HTTPException(status_code=400, detail="Mission must be in PLANNED state to replan")

    from datetime import datetime
    rejected = [s for s in mission.steps if s.state == "rejected"]
    if not rejected:
        raise HTTPException(status_code=400, detail="No rejected steps to replan")
    for step in rejected:
        step.state = "pending"
        step.approval_decision_id = None
        step.metadata["replan_reason"] = request.replan_notes
        step.metadata["replanned_at"] = datetime.utcnow().isoformat()
        step.metadata["replanned_by"] = principal.user_id
        step.updated_at = step.metadata["replanned_at"]

    store = get_governance_store()
    try:
        store.transition_mission(
            mission_id, MissionState.WAITING_APPROVAL,
            actor_id=principal.user_id,
            reason=f"Replanned: {request.replan_notes}"
        )
    except ValueError:
        pass
    get_telemetry().record_event("mission_replanned", tenant_id=principal.tenant_id,
        user_id=principal.user_id, mission_id=mission_id,
        properties={"replanned_steps": len(rejected)})
    return {"status": "replanned", "replanned_steps": len(rejected), "mission": mission.to_dict()}


# =============================================================================
# Item 9: Audit trail endpoint
# =============================================================================

@router.get("/missions/{mission_id}/audit-trail")
async def get_audit_trail(
    mission_id: str,
    principal: Principal = Depends(get_current_principal),
):
    """Return all state transition events for the mission."""
    mission = _mission_or_404(mission_id, tenant_id=principal.tenant_id)
    if mission.user_id != principal.user_id and not ({"admin", "auditor", "reviewer"} & set(principal.roles)):
        raise HTTPException(status_code=403, detail="Forbidden")
    return {
        "mission_id": mission_id,
        "events": [e.to_dict() for e in mission.trace_events],
        "event_count": len(mission.trace_events),
    }


# =============================================================================
# Item 10: Compliance breakdown endpoint
# =============================================================================

@router.get("/missions/{mission_id}/compliance")
async def get_compliance(
    mission_id: str,
    principal: Principal = Depends(get_current_principal),
):
    """Weighted compliance score with per-step breakdown."""
    mission = _mission_or_404(mission_id, tenant_id=principal.tenant_id)
    if mission.user_id != principal.user_id and not ({"admin", "auditor", "reviewer"} & set(principal.roles)):
        raise HTTPException(status_code=403, detail="Forbidden")

    risk_weights = {"low": 1, "medium": 2, "high": 3, "critical": 5}
    step_details = []
    total_weight = 0
    compliant_weight = 0
    for step in mission.steps:
        w = risk_weights.get(step.risk_level, 1)
        total_weight += w
        compliant = not step.requires_approval or bool(step.approval_decision_id)
        if compliant:
            compliant_weight += w
        step_details.append({
            "step_id": step.id,
            "title": step.title,
            "risk_level": step.risk_level,
            "weight": w,
            "requires_approval": step.requires_approval,
            "has_approval": bool(step.approval_decision_id),
            "compliant": compliant,
            "state": step.state,
        })

    overall = round((compliant_weight / total_weight) * 100, 2) if total_weight else 100.0
    return {
        "mission_id": mission_id,
        "overall_score": overall,
        "policy_version": mission.policy_version,
        "steps": step_details,
        "weights_used": risk_weights,
    }


# =============================================================================
# Item 11: Trace completeness detail endpoint
# =============================================================================

@router.get("/missions/{mission_id}/trace")
async def get_trace(
    mission_id: str,
    principal: Principal = Depends(get_current_principal),
):
    """Per-step trace completeness breakdown."""
    mission = _mission_or_404(mission_id, tenant_id=principal.tenant_id)
    if mission.user_id != principal.user_id and not ({"admin", "auditor", "reviewer"} & set(principal.roles)):
        raise HTTPException(status_code=403, detail="Forbidden")
    return {
        "mission_id": mission_id,
        "overall": mission.trace_completeness,
        "steps": [
            {
                "id": s.id,
                "title": s.title,
                "has_state": s.state != "pending",
                "current_state": s.state,
                "has_evidence": bool(s.evidence_artifact_ids),
                "evidence_count": len(s.evidence_artifact_ids),
                "has_approval": bool(s.approval_decision_id),
                "requires_approval": s.requires_approval,
                "has_timing": bool(s.metadata.get("started_at") and s.metadata.get("completed_at")),
            }
            for s in mission.steps
        ],
    }


# =============================================================================
# Item 20: Evidence chain verification endpoint
# =============================================================================

@router.get("/missions/{mission_id}/evidence/verify")
async def verify_evidence_chain(
    mission_id: str,
    principal: Principal = Depends(get_current_principal),
):
    """Item 20: Verify cryptographic chain of custody for all mission artifacts."""
    mission = _mission_or_404(mission_id, tenant_id=principal.tenant_id)
    if mission.user_id != principal.user_id and not ({"admin", "auditor"} & set(principal.roles)):
        raise HTTPException(status_code=403, detail="Forbidden")
    from ..core.evidence_vault import get_evidence_vault
    vault = get_evidence_vault()
    return vault.verify_chain(mission_id)


# =============================================================================
# Item 13: Evidence ZIP download endpoint
# =============================================================================

@router.get("/missions/{mission_id}/evidence/download")
async def download_evidence_zip(
    mission_id: str,
    principal: Principal = Depends(get_current_principal),
):
    """Item 13: Download evidence bundle as ZIP archive."""
    from fastapi.responses import Response
    mission = _mission_or_404(mission_id, tenant_id=principal.tenant_id)
    if mission.user_id != principal.user_id and not ({"admin", "auditor"} & set(principal.roles)):
        raise HTTPException(status_code=403, detail="Forbidden")
    from ..core.evidence_vault import get_evidence_vault
    vault = get_evidence_vault()
    zip_bytes = vault.export_zip(mission_id)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=evidence_{mission_id[:8]}.zip"},
    )


# =============================================================================
# Item 19: Step failure history endpoint
# =============================================================================

@router.get("/missions/{mission_id}/steps/{step_id}/failures")
async def get_step_failures(
    mission_id: str,
    step_id: str,
    principal: Principal = Depends(get_current_principal),
):
    """Item 19: Retrieve failure and retry history for a specific step."""
    mission = _mission_or_404(mission_id, tenant_id=principal.tenant_id)
    if mission.user_id != principal.user_id and not ({"admin", "auditor", "reviewer"} & set(principal.roles)):
        raise HTTPException(status_code=403, detail="Forbidden")
    step = next((s for s in mission.steps if s.id == step_id), None)
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")
    return {
        "mission_id": mission_id,
        "step_id": step_id,
        "failures": step.metadata.get("failure_history", []),
        "failure_count": len(step.metadata.get("failure_history", [])),
    }