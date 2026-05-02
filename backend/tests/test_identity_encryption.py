"""
Tests for identity encryption behavior.
"""

from types import SimpleNamespace

import pytest


def test_encryption_manager_uses_settings_secret_when_env_missing(monkeypatch):
    from backend.agent import identity

    monkeypatch.delenv("ENCRYPTION_SECRET", raising=False)
    monkeypatch.delenv("ENCRYPTION_MASTER_KEY", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setattr(
        identity,
        "get_settings",
        lambda: SimpleNamespace(
            encryption_secret="x" * 32,
            secret_key="y" * 32,
        ),
    )

    manager = identity.EncryptionManager()
    ciphertext = manager.encrypt("sensitive-value")

    assert ciphertext != "sensitive-value"
    assert manager.decrypt(ciphertext) == "sensitive-value"


def test_encryption_manager_requires_some_persistent_secret(monkeypatch):
    from backend.agent import identity

    monkeypatch.delenv("ENCRYPTION_SECRET", raising=False)
    monkeypatch.delenv("ENCRYPTION_MASTER_KEY", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setattr(
        identity,
        "get_settings",
        lambda: SimpleNamespace(encryption_secret="", secret_key=""),
    )

    with pytest.raises(RuntimeError, match="Encryption secret is required"):
        identity.EncryptionManager()
