"""
Webhook signature and replay protection helpers.
"""

from __future__ import annotations

import base64
import hmac
import hashlib
import time
from collections import OrderedDict
from typing import Mapping, Optional
from urllib.parse import urlparse

from fastapi import HTTPException, status


class ReplayGuard:
    def __init__(self, max_entries: int = 1000, ttl_seconds: int = 300):
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._seen: OrderedDict[str, float] = OrderedDict()

    def check(self, nonce: str, timestamp: int) -> bool:
        now = int(time.time())
        if abs(now - timestamp) > self.ttl_seconds:
            return False

        expired = [key for key, seen_at in self._seen.items() if now - seen_at > self.ttl_seconds]
        for key in expired:
            self._seen.pop(key, None)

        if nonce in self._seen:
            return False

        self._seen[nonce] = now
        while len(self._seen) > self.max_entries:
            self._seen.popitem(last=False)
        return True


_replay_guard = ReplayGuard()


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    if not signature or not secret:
        return False
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_telegram_secret_token(received_token: Optional[str], expected_token: str) -> bool:
    if not received_token or not expected_token:
        return False
    return hmac.compare_digest(received_token, expected_token)


def verify_twilio_signature(url: str, form_data: Mapping[str, str], signature: str, auth_token: str) -> bool:
    if not signature or not auth_token:
        return False

    parsed = urlparse(url)
    normalized_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    pieces = [normalized_url]
    for key in sorted(form_data.keys()):
        pieces.append(f"{key}{form_data[key]}")

    payload = "".join(pieces).encode("utf-8")
    expected = base64.b64encode(hmac.new(auth_token.encode("utf-8"), payload, hashlib.sha1).digest()).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def validate_webhook_request(
    *,
    payload: bytes,
    signature: str,
    secret: str,
    timestamp: Optional[int] = None,
    nonce: Optional[str] = None,
) -> None:
    if not verify_webhook_signature(payload, signature, secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")

    if timestamp is not None and nonce:
        if not _replay_guard.check(nonce, timestamp):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Webhook replay detected")


def verify_webhook_replay(*, nonce: str, timestamp: Optional[int] = None) -> bool:
    if not nonce:
        return False
    return _replay_guard.check(nonce, int(timestamp or time.time()))