from backend.core.ai_providers.kimi_provider import KimiProvider
from backend.core.ai_providers.openai_provider import OpenAIProvider


def test_kimi_and_openai_use_independent_configuration(monkeypatch):
    monkeypatch.setenv("KIMI_API_KEY", "kimi-test-key")
    monkeypatch.setenv("KIMI_BASE_URL", "https://api.moonshot.ai/v1")
    monkeypatch.setenv("KIMI_MODEL", "moonshot-v1-8k")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")

    kimi = KimiProvider()
    openai = OpenAIProvider()

    assert kimi.api_key == "kimi-test-key"
    assert kimi.base_url == "https://api.moonshot.ai/v1"
    assert kimi.config.default_model == "moonshot-v1-8k"
    assert openai.api_key == "openai-test-key"
    assert openai.base_url == "https://api.openai.com/v1"
    assert openai.config.default_model == "gpt-4o-mini"
