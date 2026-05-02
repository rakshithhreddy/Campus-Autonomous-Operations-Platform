import base64
import hashlib
import hmac
import time

import pytest


def test_telegram_secret_token_verification():
    from backend.core.webhook_security import verify_telegram_secret_token

    assert verify_telegram_secret_token("secret-123", "secret-123") is True
    assert verify_telegram_secret_token("wrong", "secret-123") is False


def test_replay_guard_rejects_duplicate_nonce():
    from backend.core.webhook_security import ReplayGuard

    guard = ReplayGuard(ttl_seconds=60)
    now = int(time.time())
    assert guard.check("nonce-1", now) is True
    assert guard.check("nonce-1", now) is False


def test_twilio_signature_verification():
    from backend.core.webhook_security import verify_twilio_signature

    url = "https://example.com/webhook/whatsapp"
    form_data = {"Body": "Hello", "From": "whatsapp:+1234567890", "To": "whatsapp:+10987654321"}
    auth_token = "twilio-token"

    normalized_url = url
    payload = normalized_url + "".join(f"{key}{form_data[key]}" for key in sorted(form_data.keys()))
    expected_signature = base64.b64encode(hmac.new(auth_token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1).digest()).decode("utf-8")

    assert verify_twilio_signature(url, form_data, expected_signature, auth_token) is True
    assert verify_twilio_signature(url, form_data, "invalid", auth_token) is False


def test_verify_webhook_replay_helper():
    from backend.core.webhook_security import verify_webhook_replay

    assert verify_webhook_replay(nonce="twilio:test-123", timestamp=int(time.time())) is True
    assert verify_webhook_replay(nonce="twilio:test-123", timestamp=int(time.time())) is False