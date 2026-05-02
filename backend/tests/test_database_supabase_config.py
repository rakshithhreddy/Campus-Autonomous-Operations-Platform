"""
Tests for Supabase database configuration behavior.
"""

from unittest.mock import MagicMock


def test_get_supabase_client_requires_explicit_configuration(monkeypatch):
    from backend import database_supabase as db

    monkeypatch.setattr(db, "_supabase_client", None)
    monkeypatch.setattr(db, "SUPABASE_AVAILABLE", True)
    monkeypatch.setattr(db, "SUPABASE_URL", "")
    monkeypatch.setattr(db, "SUPABASE_KEY", "test-key")
    create_client_mock = MagicMock()
    monkeypatch.setattr(db, "create_client", create_client_mock)

    assert db.get_supabase_client() is None
    create_client_mock.assert_not_called()


def test_get_supabase_client_initializes_when_configured(monkeypatch):
    from backend import database_supabase as db

    sentinel_client = object()
    create_client_mock = MagicMock(return_value=sentinel_client)

    monkeypatch.setattr(db, "_supabase_client", None)
    monkeypatch.setattr(db, "SUPABASE_AVAILABLE", True)
    monkeypatch.setattr(db, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(db, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(db, "create_client", create_client_mock)

    assert db.get_supabase_client() is sentinel_client
    create_client_mock.assert_called_once_with("https://example.supabase.co", "test-key")
