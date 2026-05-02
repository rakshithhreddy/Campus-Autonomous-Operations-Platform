"""
Kimi (Moonshot AI) Provider - Primary AI Provider
Uses OpenAI-compatible API at https://api.moonshot.ai/v1
Models: moonshot-v1-8k, moonshot-v1-32k, moonshot-v1-128k
"""
import os
import time
from typing import Dict, Any, List, Optional, AsyncGenerator, Union
import logging

from .base_provider import BaseAIProvider, ProviderConfig, AIResponse, ProviderStatus

try:
    from openai import AsyncOpenAI
    OPENAI_SDK_AVAILABLE = True
except ImportError:
    OPENAI_SDK_AVAILABLE = False

logger = logging.getLogger(__name__)

KIMI_BASE_URL = "https://api.moonshot.ai/v1"


class KimiProvider(BaseAIProvider):
    """
    Kimi (Moonshot AI) provider.
    OpenAI-compatible API — PRIMARY provider when KIMI_API_KEY is set.
    """

    config = ProviderConfig(
        name="kimi",
        supports_streaming=True,
        supports_vision=False,
        supports_function_calling=True,
        supports_json_mode=True,
        is_local=False,
        is_free=False,
        base_url=KIMI_BASE_URL,
        models=[
            "moonshot-v1-8k",
            "moonshot-v1-32k",
            "moonshot-v1-128k",
        ],
        default_model="moonshot-v1-8k",
        timeout=120,
        cost_per_1k_tokens=0.002,
    )

    def __init__(self):
        super().__init__()

        self.api_key = (os.getenv("KIMI_API_KEY") or "").strip()
        base_url_env = (os.getenv("KIMI_BASE_URL") or "").strip()
        self.base_url = base_url_env.rstrip("/") if base_url_env else KIMI_BASE_URL

        # Allow per-deployment model override
        model_override = (os.getenv("KIMI_MODEL") or "").strip()
        if model_override:
            self.config.default_model = model_override

        self._client: Optional[AsyncOpenAI] = None

        if self.api_key and OPENAI_SDK_AVAILABLE:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
            self._status = ProviderStatus.AVAILABLE
            logger.info(
                f"[KIMI] Initialized — base_url={self.base_url}, "
                f"default_model={self.config.default_model}"
            )
        else:
            self._status = ProviderStatus.UNAVAILABLE
            if not OPENAI_SDK_AVAILABLE:
                self._last_error = "openai package not installed"
            else:
                self._last_error = "KIMI_API_KEY not set"
            logger.warning(f"[KIMI] Unavailable: {self._last_error}")

    async def health_check(self) -> bool:
        """Verify Kimi endpoint with a minimal chat call."""
        if not self._client:
            return False
        try:
            await self._client.chat.completions.create(
                model=self.config.default_model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
                temperature=0,
            )
            self._status = ProviderStatus.AVAILABLE
            self._reset_errors()
            return True
        except Exception as e:
            self._status = ProviderStatus.UNAVAILABLE
            self._record_error(str(e))
            logger.warning(f"[KIMI] Health check failed: {e}")
            return False

    def supports_model(self, model: str) -> bool:
        """Accept any moonshot-* model string."""
        if model and model.startswith("moonshot"):
            return True
        return super().supports_model(model)

    async def generate(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
        json_mode: bool = False,
        **kwargs,
    ) -> Union[AIResponse, AsyncGenerator[str, None]]:
        """Generate completion using Kimi (Moonshot) API."""

        if not self._client:
            raise Exception("Kimi client not initialized — KIMI_API_KEY missing or openai package absent")

        model = model or self.config.default_model
        start_time = time.time()

        params: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        if json_mode:
            params["response_format"] = {"type": "json_object"}

        if "tools" in kwargs:
            params["tools"] = kwargs["tools"]
        if "tool_choice" in kwargs:
            params["tool_choice"] = kwargs["tool_choice"]

        try:
            if stream:
                return self._stream_generate(params, model, start_time)

            response = await self._client.chat.completions.create(**params)

            latency_ms = (time.time() - start_time) * 1000
            self._record_latency(latency_ms)
            self._reset_errors()

            choice = response.choices[0]

            return AIResponse(
                content=choice.message.content or "",
                model=model,
                provider="kimi",
                usage={
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                },
                finish_reason=choice.finish_reason or "stop",
                latency_ms=latency_ms,
                raw_response=response.model_dump(),
            )

        except Exception as e:
            self._record_error(str(e))
            raise

    async def _stream_generate(
        self,
        params: Dict[str, Any],
        model: str,
        start_time: float,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from Kimi."""
        try:
            stream = await self._client.chat.completions.create(**params)
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

            self._record_latency((time.time() - start_time) * 1000)
            self._reset_errors()

        except Exception as e:
            self._record_error(str(e))
            raise

    async def generate_embedding(
        self,
        text: Union[str, List[str]],
        model: Optional[str] = None,
    ) -> List[List[float]]:
        raise NotImplementedError("Kimi does not support embeddings via this provider")


# Singleton
_kimi_provider: Optional[KimiProvider] = None


def get_kimi_provider() -> KimiProvider:
    """Get or create the global Kimi provider singleton."""
    global _kimi_provider
    if _kimi_provider is None:
        _kimi_provider = KimiProvider()
    return _kimi_provider
