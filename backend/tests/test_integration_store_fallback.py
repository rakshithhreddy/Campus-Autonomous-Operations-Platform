"""
Tests for integration store fallback behavior.
"""

from unittest.mock import MagicMock


def test_store_integration_falls_back_to_memory_on_supabase_error(monkeypatch):
    from backend.core.integration_manager.integration_store import IntegrationStore

    store = IntegrationStore()
    store.supabase = MagicMock()
    store.supabase.table.return_value.upsert.return_value.execute.side_effect = Exception("db down")

    result = store.store_integration(
        user_id="user-123",
        provider="zoom",
        token_data={"access_token": "abc", "refresh_token": "def"},
        scopes=["meeting:write"],
    )

    assert result is True
    record = store.get_integration("user-123", "zoom")
    assert record is not None
    assert record["provider"] == "zoom"
    assert record["status"] == "connected"
    assert record["tokens"]["access_token"] == "abc"


def test_get_user_integrations_merges_memory_fallback(monkeypatch):
    from backend.core.integration_manager.integration_store import IntegrationStore

    store = IntegrationStore()
    store.supabase = MagicMock()
    store.supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = Exception("db down")
    store._memory_store = {
        "user-123": {
            "zoom": {
                "id": "mem-user-123-zoom",
                "user_id": "user-123",
                "provider": "zoom",
                "status": "connected",
                "encrypted_tokens": None,
                "scopes": ["meeting:write"],
                "metadata": {},
                "updated_at": "2026-04-29T00:00:00Z",
            }
        }
    }

    connected = store.get_user_integrations("user-123")
    services = {item["service"] for item in connected}

    assert "zoom" in services
