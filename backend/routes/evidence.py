"""
Evidence API routes for storing and exporting mission artifacts.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..core.auth import Principal, get_current_principal
from ..core.evidence_vault import get_evidence_vault
from ..core.governance_store import get_governance_store
from ..core.security import DataMasker


router = APIRouter(prefix="/api/evidence", tags=["evidence"])


class EvidenceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    content_type: str = "text/plain"
    step_id: Optional[str] = None
    classification: str = Field(default="internal", pattern="^(public|internal|confidential|restricted)$")
    metadata: Dict[str, Any] = Field(default_factory=dict)


def _redact_artifact_payload(artifact_payload: Dict[str, Any]) -> Dict[str, Any]:
    safe_payload = dict(artifact_payload)
    if "file_path" in safe_payload:
        safe_payload["file_path"] = DataMasker.mask_string(str(safe_payload["file_path"]), visible_chars=2)
    if "metadata" in safe_payload and isinstance(safe_payload["metadata"], dict):
        safe_payload["metadata"] = DataMasker.mask_dict(safe_payload["metadata"], additional_keys={"email"})
    if "name" in safe_payload:
        safe_payload["name"] = DataMasker.mask_pii(str(safe_payload["name"]))
    return safe_payload


@router.post("/missions/{mission_id}/artifacts")
async def create_artifact(mission_id: str, request: EvidenceCreateRequest, principal: Principal = Depends(get_current_principal)):
    mission = get_governance_store().get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission.user_id != principal.user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    artifact = get_evidence_vault().store_artifact(
        mission_id=mission_id,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        step_id=request.step_id,
        name=request.name,
        content=request.content,
        content_type=request.content_type,
        classification=request.classification,
        metadata=request.metadata,
    )
    if request.step_id:
        step = next((item for item in mission.steps if item.id == request.step_id), None)
        if step:
            step.evidence_artifact_ids.append(artifact.artifact_id)
    mission.evidence_artifact_ids.append(artifact.artifact_id)
    return _redact_artifact_payload(artifact.to_dict())


@router.get("/missions/{mission_id}/artifacts")
async def list_artifacts(
    mission_id: str,
    include_expired: bool = Query(True, description="Include artifacts past retention expiry"),
    principal: Principal = Depends(get_current_principal),
):
    mission = get_governance_store().get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission.user_id != principal.user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    artifacts = get_evidence_vault().list_artifacts(mission_id, include_expired=include_expired)
    return {"artifacts": [_redact_artifact_payload(item) for item in artifacts]}


@router.get("/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str, principal: Principal = Depends(get_current_principal)):
    artifact = get_evidence_vault().get_artifact(artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    if artifact.tenant_id != principal.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return _redact_artifact_payload(artifact.to_dict())


@router.get("/missions/{mission_id}/bundle")
async def export_bundle(
    mission_id: str,
    include_expired: bool = Query(True, description="Include expired artifacts in export payload"),
    principal: Principal = Depends(get_current_principal),
):
    mission = get_governance_store().get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission.user_id != principal.user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    payload = get_evidence_vault().export_download_payload(mission_id, include_expired=include_expired)
    manifest = dict(payload.get("manifest") or {})
    manifest["artifacts"] = [_redact_artifact_payload(item) for item in manifest.get("artifacts", [])]
    payload["manifest"] = manifest
    return payload