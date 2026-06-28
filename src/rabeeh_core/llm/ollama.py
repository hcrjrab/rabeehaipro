"""Ollama adapter (local models: Qwen, DeepSeek, Llama, ...).

Talks to the local Ollama HTTP API (``/api/chat``) via ``httpx``. Ollama is
the primary provider in the "prefer local" posture of the project: it keeps
data on-device and supports the model families we route between.

Streaming
---------
``chat_stream`` uses Ollama's native ``"stream": True`` mode and yields
chunks as they arrive, then a final ``done`` event with accumulated usage.

Capabilities
------------
Reported dynamically by pattern-matching the model name against the
:mod:`capabilities` registry.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config.settings import Settings
from .base import LLMMessage, LLMResponse, LLMStreamEvent, LLMUsage, ModelCapabilities
from .capabilities import cached_detect

_log = logging.getLogger(__name__)


class OllamaLLMClient:
    """Async adapter over the Ollama ``/api/chat`` endpoint."""

    name: str = "ollama"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.ollama_default_model
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Lazy-init the HTTP client so import-time never opens sockets."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._settings.request_timeout_seconds,
            )
        return self._client

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        client = await self._ensure_client()
        payload: dict[str, Any] = {
            "model": kwargs.get("model", self._model),
            "messages": [
                {"role": m.role, "content": m.content, **({"name": m.name} if m.name else {})}
                for m in messages
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
                **({"num_predict": max_tokens} if max_tokens else {}),
            },
        }
        if tools:
            payload["tools"] = tools

        try:
            resp = await client.post("/api/chat", json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            _log.error("Ollama chat failed: %s", exc)
            raise

        data = resp.json()
        content = data.get("message", {}).get("content", "")
        usage = LLMUsage(
            prompt_tokens=int(data.get("prompt_eval_count", 0) or 0),
            completion_tokens=int(data.get("eval_count", 0) or 0),
        )
        usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
        return LLMResponse(
            content=content,
            usage=usage,
            model=payload["model"],
            provider=self.name,
            raw=data,
            finish_reason="stop",
        )

    async def chat_stream(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Stream from Ollama's ``/api/chat`` with ``stream: True``."""
        client = await self._ensure_client()
        payload: dict[str, Any] = {
            "model": kwargs.get("model", self._model),
            "messages": [
                {"role": m.role, "content": m.content, **({"name": m.name} if m.name else {})}
                for m in messages
            ],
            "stream": True,
            "options": {
                "temperature": temperature,
                **({"num_predict": max_tokens} if max_tokens else {}),
            },
        }
        if tools:
            payload["tools"] = tools

        accumulated = ""
        prompt_tokens = 0
        completion_tokens = 0

        try:
            async with client.stream("POST", "/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    import json as _json

                    try:
                        chunk = _json.loads(line)
                    except _json.JSONDecodeError:
                        continue

                    if "message" in chunk:
                        delta = chunk["message"].get("content", "")
                        if delta:
                            accumulated += delta
                            yield LLMStreamEvent(
                                kind="chunk",
                                content=delta,
                                model=payload["model"],
                                provider=self.name,
                            )

                    # Track token usage from the final response.
                    if chunk.get("done"):
                        prompt_tokens = int(chunk.get("prompt_eval_count", 0) or 0)
                        completion_tokens = int(chunk.get("eval_count", 0) or 0)

        except httpx.HTTPError as exc:
            yield LLMStreamEvent(
                kind="error",
                error=f"Ollama streaming failed: {exc}",
                model=payload["model"],
                provider=self.name,
            )
            return

        usage = LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

        yield LLMStreamEvent(
            kind="done",
            content=accumulated,
            usage=usage,
            model=payload["model"],
            provider=self.name,
            finish_reason="stop",
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def get_capabilities(self) -> ModelCapabilities:
        return cached_detect(self._model)
