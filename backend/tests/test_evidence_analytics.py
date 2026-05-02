import pytest


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    from backend.core import governance_store as governance_store_module
    from backend.core import evidence_vault as evidence_vault_module
    from backend.core import telemetry as telemetry_module

    governance_store_module._governance_store = None
    evidence_vault_module._evidence_vault = None
    telemetry_module._telemetry = None
    monkeypatch.setenv("EVIDENCE_RETENTION_DAYS", "30")
    yield


def _create_mission(client, auth_headers):
    response = client.post(
        "/api/governance/missions",
        json={
            "title": "Evidence mission",
            "description": "Retention and analytics",
            "steps": [
                {
                    "title": "Collect artifact",
                    "description": "Create immutable artifact",
                    "action_type": "evidence_intake",
                    "risk_level": "medium",
                    "requires_approval": False,
                }
            ],
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    return response.json()


def test_evidence_bundle_includes_chain_and_retention(client, auth_headers):
    mission = _create_mission(client, auth_headers)

    create = client.post(
        f"/api/evidence/missions/{mission['mission_id']}/artifacts",
        json={
            "name": "artifact-1-user@example.com.txt",
            "content": "trusted evidence",
            "content_type": "text/plain",
            "classification": "internal",
            "metadata": {"owner_email": "owner@example.com", "api_key": "abcdef123456"},
        },
        headers=auth_headers,
    )
    assert create.status_code == 200
    created_payload = create.json()
    assert "***" in created_payload["file_path"]
    assert created_payload["metadata"]["api_key"] != "abcdef123456"
    assert "@" in created_payload["name"]
    assert "example.com" in created_payload["name"]

    bundle = client.get(f"/api/evidence/missions/{mission['mission_id']}/bundle", headers=auth_headers)
    assert bundle.status_code == 200
    manifest = bundle.json()["manifest"]

    assert "chain_of_custody" in manifest
    assert manifest["artifact_count"] == 1
    assert manifest["retention_policy"]["retention_days"] == 30
    assert manifest["artifacts"][0]["metadata"]["retention_days"] == 30
    assert manifest["artifacts"][0]["metadata"].get("expires_at")
    assert manifest["artifacts"][0]["metadata"]["owner_email"] != "owner@example.com"


def test_differentiation_and_procurement_analytics(client, auth_headers):
    mission = _create_mission(client, auth_headers)

    from backend.core.telemetry import get_telemetry

    telemetry = get_telemetry()
    telemetry.record_event(
        "mission_completed",
        tenant_id="test-tenant",
        user_id="test-user-123",
        mission_id=mission["mission_id"],
        properties={"approval_latency_ms": 1200, "fallback_strategy": "manual_review"},
    )
    telemetry.record_event(
        "procurement_competitive_signal",
        tenant_id="test-tenant",
        user_id="test-user-123",
        mission_id=mission["mission_id"],
        properties={"reason": "auditability"},
    )

    diff = client.get("/api/analytics/differentiation", headers=auth_headers)
    assert diff.status_code == 200
    diff_data = diff.json()
    assert "governed_execution" in diff_data
    assert "suggestion_only" in diff_data
    assert "delta" in diff_data
    assert diff_data["governed_execution"]["trace_completeness"] >= 0
    assert "mission_success_rate_delta" in diff_data["delta"]

    proof = client.get("/api/analytics/procurement-proof", headers=auth_headers)
    assert proof.status_code == 200
    proof_data = proof.json()
    assert "proof_protocol" in proof_data
    assert "competitive_reasons" in proof_data
    assert proof_data["competitive_reasons"].get("auditability") == 1
