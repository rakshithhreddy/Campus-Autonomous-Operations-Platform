"""
OpenAI Provider - GPT-4, GPT-4o, o1 models
High capability fallback provider
"""
import os
import time
from typing import Dict, Any, List, Optional, AsyncGenerator, Union
import json

from .base_provider import BaseAIProvider, ProviderConfig, AIResponse, ProviderStatus
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class OpenAIProvider(BaseAIProvider):
    """
    OpenAI API provider.
    Supports GPT-4, GPT-4o, o1 models.
    """
    
    config = ProviderConfig(
        name="openai",
        supports_streaming=True,
        supports_vision=True,
        supports_function_calling=True,
        supports_json_mode=True,
        is_local=False,
        is_free=False,
        base_url="https://api.openai.com/v1",
        models=[
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4-turbo-preview",
            "gpt-4",
            "gpt-3.5-turbo",
            "o1-preview",
            "o1-mini",
        ],
        default_model="gpt-4o-mini",
        timeout=120,
        cost_per_1k_tokens=0.01  # Varies by model
    )
    
    def __init__(self):
        super().__init__()

        # OpenAI is an independent fallback; Kimi has its own provider.
        self.api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        self.base_url = (
            os.getenv("OPENAI_BASE_URL") or self.config.base_url
        ).strip().rstrip("/")
        self.config.default_model = (
            os.getenv("OPENAI_MODEL") or self.config.default_model
        ).strip()

        self._client = None

        if self.api_key and OPENAI_AVAILABLE:
            # `base_url` enables OpenAI-compatible providers.
            self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
            self._status = ProviderStatus.AVAILABLE
        else:
            self._status = ProviderStatus.UNAVAILABLE
            if not OPENAI_AVAILABLE:
                self._last_error = "openai package not installed"
            else:
                self._last_error = "OPENAI_API_KEY not set"
    
    async def health_check(self) -> bool:
        """Check if the OpenAI-compatible API is accessible.

        Many OpenAI-compatible providers (including some Kimi deployments) may not
        fully support the /models endpoint, so we do a tiny chat call instead.
        """
        if not self._client:
            return False

        try:
            await self._client.chat.completions.create(
                model=self.config.default_model or "gpt-4o-mini",
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
                temperature=0,
            )
            self._status = ProviderStatus.AVAILABLE
            return True
        except Exception as e:
            self._status = ProviderStatus.UNAVAILABLE
            self._record_error(str(e))
            return False
    
    def supports_model(self, model: str) -> bool:
        """OpenAI-compatible endpoints may expose provider-specific model IDs.

        If the base_url is overridden (e.g. Kimi), allow any model string.
        """

        if getattr(self, "base_url", None) and self.base_url.rstrip("/") != self.config.base_url.rstrip("/"):
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
        **kwargs
    ) -> Union[AIResponse, AsyncGenerator[str, None]]:
        """Generate completion using OpenAI-compatible API"""
        
        if not self._client:
            raise Exception("OpenAI client not initialized")
        
        model = model or self.config.default_model
        start_time = time.time()
        
        # Build request params
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream
        }
        
        # o1 models don't support temperature
        if model.startswith("o1"):
            del params["temperature"]
        
        if json_mode and not model.startswith("o1"):
            params["response_format"] = {"type": "json_object"}
        
        # Add function calling if provided
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
                provider="openai",
                usage={
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0
                },
                finish_reason=choice.finish_reason or "stop",
                latency_ms=latency_ms,
                raw_response=response.model_dump()
            )
            
        except Exception as e:
            self._record_error(str(e))
            raise
    
    async def _stream_generate(
        self,
        params: Dict[str, Any],
        model: str,
        start_time: float
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from OpenAI"""
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
        model: Optional[str] = None
    ) -> List[List[float]]:
        """Generate embeddings using OpenAI"""
        if not self._client:
            raise Exception("OpenAI client not initialized")
        
        model = model or "text-embedding-3-small"
        texts = [text] if isinstance(text, str) else text
        
        try:
            response = await self._client.embeddings.create(
                model=model,
                input=texts
            )
            return [d.embedding for d in response.data]
        except Exception as e:
            self._record_error(str(e))
            raise


# Singleton
_openai_provider: Optional[OpenAIProvider] = None


def get_openai_provider() -> OpenAIProvider:
    """Get or create OpenAI provider singleton"""
    global _openai_provider
    if _openai_provider is None:
        _openai_provider = OpenAIProvider()
    return _openai_provider
