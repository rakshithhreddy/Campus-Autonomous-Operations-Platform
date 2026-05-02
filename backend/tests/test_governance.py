import pytest


@pytest.fixture(autouse=True)
def reset_governance_state():
    from backend.core import governance_store as governance_store_module
    from backend.core import evidence_vault as evidence_vault_module
    from backend.core import telemetry as telemetry_module

    governance_store_module._governance_store = None
    evidence_vault_module._evidence_vault = None
    telemetry_module._telemetry = None
    yield


def _create_high_risk_mission(client, auth_headers):
    response = client.post(
        "/api/governance/missions",
        json={
            "title": "Send procurement email",
            "description": "High-risk external communication",
            "steps": [
                {
                    "title": "Send approval email",
                    "description": "Notify vendor",
                    "action_type": "send_email",
                    "risk_level": "high",
                    "requires_approval": True,
                    "approver_roles": ["manager"],
                }
            ],
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    return response.json()


def test_mission_creation_requires_approval(client, auth_headers):
    mission = _create_high_risk_mission(client, auth_headers)

    assert mission["state"] == "waiting_approval"
    assert len(mission["steps"]) == 1
    assert mission["steps"][0]["requires_approval"] is True

    approvals = client.get("/api/governance/approvals", headers=auth_headers)
    assert approvals.status_code == 200
    approval_items = approvals.json()["approvals"]
    assert len(approval_items) == 1


def test_approval_records_and_advances_mission(client, auth_headers):
    mission = _create_high_risk_mission(client, auth_headers)
    step_id = mission["steps"][0]["id"]

    approval = client.post(
        f"/api/governance/missions/{mission['mission_id']}/approval",
        json={"step_id": step_id, "decision": "approve", "reason": "Reviewed and approved"},
        headers=auth_headers,
    )
    assert approval.status_code == 200
    approval_data = approval.json()
    assert approval_data["approval"]["decision"] == "approve"

    refreshed = client.get(f"/api/governance/missions/{mission['mission_id']}", headers=auth_headers)
    assert refreshed.status_code == 200
    refreshed_mission = refreshed.json()
    assert refreshed_mission["steps"][0]["approval_decision_id"] is not None
    assert refreshed_mission["state"] in ["running", "planned"]


def test_evidence_bundle_and_trust_metrics(client, auth_headers):
    mission = _create_high_risk_mission(client, auth_headers)
    step_id = mission["steps"][0]["id"]

    artifact = client.post(
        f"/api/evidence/missions/{mission['mission_id']}/artifacts",
        json={
            "name": "approval-note.txt",
            "content": "Approved after policy review",
            "content_type": "text/plain",
            "step_id": step_id,
            "classification": "internal",
        },
        headers=auth_headers,
    )
    assert artifact.status_code == 200

    bundle = client.get(f"/api/evidence/missions/{mission['mission_id']}/bundle", headers=auth_headers)
    assert bundle.status_code == 200
    bundle_data = bundle.json()
    assert bundle_data["manifest"]["artifact_count"] == 1

    trust = client.get("/api/governance/trust", headers=auth_headers)
    assert trust.status_code == 200
    trust_data = trust.json()
    assert trust_data["mission_count"] >= 1
    assert trust_data["trace_completeness"] >= 0


def test_policy_rule_creation(client, auth_headers):
    response = client.post(
        "/api/policies",
        json={
            "name": "Vendor email approval",
            "risk_level": "high",
            "keywords": ["vendor", "email"],
            "required_roles": ["manager"],
            "min_approvals": 1,
            "active": True,
            "version": "v1",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    rule = response.json()
    assert rule["name"] == "Vendor email approval"
    assert rule["active"] is True


def test_workflow_pack_list_and_create_mission(client, auth_headers):
    packs_response = client.get("/api/governance/workflow-packs", headers=auth_headers)
    assert packs_response.status_code == 200
    packs = packs_response.json()["packs"]
    assert len(packs) >= 3

    create_response = client.post(
        "/api/governance/missions/from-pack",
        json={"pack_id": "accreditation"},
        headers=auth_headers,
    )
    assert create_response.status_code == 200
    mission = create_response.json()
    assert mission["title"]
    assert len(mission["steps"]) >= 1
    assert any(step["action_type"] == "export_bundle" for step in mission["steps"])


def test_mission_creation_is_idempotent_for_same_key(client, auth_headers):
    payload = {
        "title": "Idempotent Mission",
        "description": "Should be created once",
        "steps": [
            {
                "title": "Step 1",
                "description": "Any",
                "action_type": "notify",
                "risk_level": "low",
                "requires_approval": False,
            }
        ],
    }
    first = client.post(
        "/api/governance/missions",
        json=payload,
        headers={**auth_headers, "X-Idempotency-Key": "mission-key-1"},
    )
    second = client.post(
        "/api/governance/missions",
        json=payload,
        headers={**auth_headers, "X-Idempotency-Key": "mission-key-1"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["mission_id"] == second.json()["mission_id"]


def test_critical_step_requires_multiple_approvals(client, auth_headers):
    mission_response = client.post(
        "/api/governance/missions",
        json={
            "title": "Critical remediation",
            "description": "Needs multi-approval",
            "steps": [
                {
                    "title": "Apply critical remediation",
                    "description": "Credential and payment system mutation",
                    "action_type": "payment_credential_update",
                    "risk_level": "critical",
                    "requires_approval": True,
                    "approver_roles": ["manager", "reviewer"],
                }
            ],
        },
        headers=auth_headers,
    )
    assert mission_response.status_code == 200
    mission = mission_response.json()
    step_id = mission["steps"][0]["id"]

    first_approval = client.post(
        f"/api/governance/missions/{mission['mission_id']}/approval",
        json={"step_id": step_id, "decision": "approve", "reason": "Manager reviewed"},
        headers=auth_headers,
    )
    assert first_approval.status_code == 200
    assert first_approval.json()["required_approvals"] >= 2
    assert first_approval.json()["current_approvals"] == 1

    reviewer_headers = {
        "Content-Type": "application/json",
        "X-Dev-User-Id": "reviewer-user",
        "X-Dev-Tenant-Id": "test-tenant",
        "X-Dev-Roles": "reviewer",
    }
    second_approval = client.post(
        f"/api/governance/missions/{mission['mission_id']}/approval",
        json={"step_id": step_id, "decision": "approve", "reason": "Reviewer approved"},
        headers=reviewer_headers,
    )
    assert second_approval.status_code == 200
    assert second_approval.json()["current_approvals"] >= 2

    refreshed = client.get(f"/api/governance/missions/{mission['mission_id']}", headers=auth_headers)
    assert refreshed.status_code == 200
    assert refreshed.json()["steps"][0]["approval_decision_id"] is not None


def test_record_step_failure_metadata(client, auth_headers):
    mission = _create_high_risk_mission(client, auth_headers)
    step_id = mission["steps"][0]["id"]

    failure = client.post(
        f"/api/governance/missions/{mission['mission_id']}/steps/failure",
        json={
            "step_id": step_id,
            "reason": "Integration timeout",
            "retry_strategy": "exponential_backoff",
            "fallback_strategy": "manual_review",
            "metadata": {"attempt": 3},
        },
        headers=auth_headers,
    )
    assert failure.status_code == 200
    data = failure.json()["failure"]
    assert data["retry_strategy"] == "exponential_backoff"
    assert data["fallback_strategy"] == "manual_review"


def test_manual_override_reviewer_visibility(client, auth_headers):
    mission = _create_high_risk_mission(client, auth_headers)
    step_id = mission["steps"][0]["id"]

    override_response = client.post(
        f"/api/governance/missions/{mission['mission_id']}/override",
        json={
            "step_id": step_id,
            "reason": "Emergency campus requirement",
            "override_action": "force_continue",
            "reviewer_visibility_notes": "Approved in incident bridge",
        },
        headers=auth_headers,
    )
    assert override_response.status_code == 200

    non_reviewer_headers = {
        "Content-Type": "application/json",
        "X-Dev-User-Id": "plain-user",
        "X-Dev-Tenant-Id": "test-tenant",
        "X-Dev-Roles": "user",
    }
    forbidden = client.get(f"/api/governance/missions/{mission['mission_id']}/overrides", headers=non_reviewer_headers)
    assert forbidden.status_code == 403

    reviewer_headers = {
        "Content-Type": "application/json",
        "X-Dev-User-Id": "auditor-user",
        "X-Dev-Tenant-Id": "test-tenant",
        "X-Dev-Roles": "auditor",
    }
    allowed = client.get(f"/api/governance/missions/{mission['mission_id']}/overrides", headers=reviewer_headers)
    assert allowed.status_code == 200
    assert len(allowed.json()["overrides"]) == 1