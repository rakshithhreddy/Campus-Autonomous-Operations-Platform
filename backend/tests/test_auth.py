import pytest

from backend.config import Settings


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    from backend.core import governance_store as governance_store_module
    from backend.core import evidence_vault as evidence_vault_module
    from backend.core import telemetry as telemetry_module

    governance_store_module._governance_store = None
    evidence_vault_module._evidence_vault = None
    telemetry_module._telemetry = None
    monkeypatch.setenv("APP_ENV", "testing")
    yield


def _create_mission(client, auth_headers):
    response = client.post(
        "/api/governance/missions",
        json={
            "title": "Auth mission",
            "description": "Auth matrix coverage",
            "steps": [
                {
                    "title": "Approve action",
                    "description": "Sensitive step",
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


def test_dev_headers_resolve_principal_in_testing(client, auth_headers):
    response = client.get("/api/governance/trust", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["mission_count"] == 0


def test_missing_auth_is_rejected_outside_dev(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")

    response = client.get("/api/governance/trust")
    assert response.status_code == 401


def test_tenant_isolation_blocks_cross_tenant_evidence_access(client, auth_headers):
    mission = _create_mission(client, auth_headers)
    create_artifact = client.post(
        f"/api/evidence/missions/{mission['mission_id']}/artifacts",
        json={
            "name": "evidence-note.txt",
            "content": "tenant-bound evidence",
            "content_type": "text/plain",
            "classification": "internal",
        },
        headers=auth_headers,
    )
    assert create_artifact.status_code == 200

    other_tenant_headers = {
        "Content-Type": "application/json",
        "X-Dev-User-Id": "other-user",
        "X-Dev-Tenant-Id": "other-tenant",
        "X-Dev-Roles": "admin",
    }

    forbidden = client.get(f"/api/evidence/missions/{mission['mission_id']}/bundle", headers=other_tenant_headers)
    assert forbidden.status_code == 403


def test_role_gate_blocks_manual_override_for_non_privileged_user(client):
    user_headers = {
        "Content-Type": "application/json",
        "X-Dev-User-Id": "standard-user",
        "X-Dev-Tenant-Id": "test-tenant",
        "X-Dev-Roles": "user",
    }
    mission = _create_mission(client, user_headers)
    step_id = mission["steps"][0]["id"]

    response = client.post(
        f"/api/governance/missions/{mission['mission_id']}/override",
        json={
            "step_id": step_id,
            "reason": "Emergency",
            "override_action": "force_continue",
        },
        headers=user_headers,
    )
    assert response.status_code == 403


def test_settings_validation_flags_default_secret_in_production(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_MASTER_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-supabase-key")

    settings = Settings(
        app_env="production",
        secret_key="change-me-in-production",
        encryption_secret="x" * 32,
        openai_api_key="test-openai-key",
        supabase_url="https://example.supabase.co",
        supabase_key="test-supabase-key",
    )

    missing = settings.validate_required()
    assert "SECRET_KEY (must be changed from default)" in missing