"""
Trust and KPI analytics routes.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends

from ..core.auth import Principal, get_current_principal
from ..core.governance_store import get_governance_store
from ..core.telemetry import get_telemetry


router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/kpi_baseline")
async def kpi_baseline(team: Optional[str] = None, principal: Principal = Depends(get_current_principal)):
    store = get_governance_store()
    summary = store.get_trust_summary(tenant_id=principal.tenant_id, user_id=principal.user_id)
    baseline = {
        "mission_success_rate": float(os.getenv("KPI_BASELINE_MISSION_SUCCESS_RATE", "70")),
        "fallback_frequency": float(os.getenv("KPI_BASELINE_FALLBACK_FREQUENCY", "12")),
        "average_approval_latency_ms": float(os.getenv("KPI_BASELINE_APPROVAL_LATENCY_MS", "1800")),
    }
    telemetry = get_telemetry().summarize_with_baseline(principal.tenant_id, baseline=baseline)
    return {
        "team": team or principal.tenant_id,
        "mission_success_rate": summary["policy_compliance"],
        "trace_completeness": summary["trace_completeness"],
        "approval_compliance": summary["policy_compliance"],
        "approval_backlog": summary["approval_backlog"],
        "mission_states": summary["mission_states"],
        "telemetry": telemetry,
    }


@router.get("/trust")
async def trust_metrics(principal: Principal = Depends(get_current_principal)):
    store = get_governance_store()
    summary = store.get_trust_summary(tenant_id=principal.tenant_id, user_id=principal.user_id)
    summary["telemetry"] = get_telemetry().summarize(principal.tenant_id)
    return summary


@router.get("/differentiation")
async def differentiation_metrics(principal: Principal = Depends(get_current_principal)):
    store = get_governance_store()
    trust = store.get_trust_summary(tenant_id=principal.tenant_id, user_id=principal.user_id)
    telemetry = get_telemetry().summarize_with_baseline(
        principal.tenant_id,
        baseline={
            "mission_success_rate": float(os.getenv("SUGGESTION_ONLY_SUCCESS_RATE", "58")),
            "fallback_frequency": float(os.getenv("SUGGESTION_ONLY_FALLBACK_FREQUENCY", "22")),
            "average_approval_latency_ms": float(os.getenv("SUGGESTION_ONLY_APPROVAL_LATENCY_MS", "2400")),
        },
    )

    governed_execution = {
        "trace_completeness": trust["trace_completeness"],
        "policy_compliance": trust["policy_compliance"],
        "approval_backlog": trust["approval_backlog"],
        "mission_success_rate": telemetry["mission_success_rate"],
        "fallback_frequency": telemetry["fallback_frequency"],
    }
    suggestion_only = {
        "trace_completeness": 0.0,
        "policy_compliance": 0.0,
        "approval_backlog": 0,
        "mission_success_rate": telemetry["baseline"]["mission_success_rate"],
        "fallback_frequency": telemetry["baseline"]["fallback_frequency"],
    }
    delta = {
        "trace_completeness_delta": round(governed_execution["trace_completeness"] - suggestion_only["trace_completeness"], 2),
        "policy_compliance_delta": round(governed_execution["policy_compliance"] - suggestion_only["policy_compliance"], 2),
        "mission_success_rate_delta": round(governed_execution["mission_success_rate"] - suggestion_only["mission_success_rate"], 2),
        "fallback_frequency_delta": round(governed_execution["fallback_frequency"] - suggestion_only["fallback_frequency"], 2),
    }

    return {
        "governed_execution": governed_execution,
        "suggestion_only": suggestion_only,
        "delta": delta,
    }


@router.get("/procurement-proof")
async def procurement_proof(principal: Principal = Depends(get_current_principal)):
    trust = get_governance_store().get_trust_summary(tenant_id=principal.tenant_id, user_id=principal.user_id)
    telemetry = get_telemetry().summarize(principal.tenant_id)
    return {
        "tenant": principal.tenant_id,
        "mission_count": trust["mission_count"],
        "trace_completeness": trust["trace_completeness"],
        "policy_compliance": trust["policy_compliance"],
        "approval_backlog": trust["approval_backlog"],
        "mission_success_rate": telemetry.get("mission_success_rate", 0.0),
        "fallback_frequency": telemetry.get("fallback_frequency", 0.0),
        "competitive_reasons": telemetry.get("competitive_reasons", {}),
        "proof_protocol": [
            "mission_trace",
            "approval_decisions",
            "evidence_bundle",
            "policy_compliance",
            "baseline_delta",
        ],
    }