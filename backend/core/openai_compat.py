"""OpenAI-compatible configuration helpers.

This project historically hard-coded OpenAI endpoints/keys. Kimi (Moonshot) exposes an
OpenAI-compatible API, so we treat it as an OpenAI-compatible provider.

Rules:
- Prefer KIMI_* env vars when present.
- Fall back to OPENAI_* env vars for backward compatibility.
- Never hard-code secrets in source.
"""

from __future__ import annotations

import os
from typing import Optional

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_KIMI_BASE_URL = "https://api.moonshot.ai/v1"

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_KIMI_MODEL = "moonshot-v1-8k"


def _clean(value: Optional[str]) -> str:
    return (value or "").strip()


def get_openai_compatible_api_key() -> str:
    """Return the API key for the OpenAI-compatible endpoint.

    If KIMI_API_KEY is set, it is used as the global key across the project.
    """

    return _clean(os.getenv("KIMI_API_KEY")) or _clean(os.getenv("OPENAI_API_KEY"))


def get_openai_compatible_base_url() -> str:
    """Return the OpenAI-compatible base URL (ending with /v1, no trailing slash)."""

    # If the user set a Kimi key, default to Kimi base URL.
    if _clean(os.getenv("KIMI_API_KEY")):
        base = _clean(os.getenv("KIMI_BASE_URL")) or _clean(os.getenv("OPENAI_BASE_URL")) or DEFAULT_KIMI_BASE_URL
    else:
        base = _clean(os.getenv("OPENAI_BASE_URL")) or _clean(os.getenv("KIMI_BASE_URL")) or DEFAULT_OPENAI_BASE_URL

    return base.rstrip("/")


def get_openai_compatible_model() -> str:
    """Return the default chat model for the OpenAI-compatible endpoint."""

    # If Kimi is configured, prefer KIMI_MODEL and ignore OPENAI_MODEL
    # (since OpenAI model names like gpt-4o-mini don't exist on Kimi)
    if _clean(os.getenv("KIMI_API_KEY")):
        return _clean(os.getenv("KIMI_MODEL")) or DEFAULT_KIMI_MODEL

    return _clean(os.getenv("OPENAI_MODEL")) or DEFAULT_OPENAI_MODEL


def build_openai_compatible_url(path: str) -> str:
    """Build a full URL for OpenAI-compatible HTTP endpoints."""

    base = get_openai_compatible_base_url()
    return f"{base}/{path.lstrip('/')}"


def is_kimi_configured() -> bool:
    return bool(_clean(os.getenv("KIMI_API_KEY")))
