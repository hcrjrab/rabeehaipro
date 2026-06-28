"""OpenRouter adapter (cloud fallback / specialised models).

OpenRouter exposes an OpenAI-compatible ``/chat/completions`` endpoint that
routes to dozens of providers behind one key. We use it as the cloud tier:

- Fallback when a local model is unavailable or times out.
- Specialised routing (e.g. vision-capable models) chosen by the router.

Secrets come from settings (``RABEEH_OPENROUTER_API_KEY``); never hardcoded.

Streaming
---------
``chat_stream`` uses SSE (``stream=True``) and yields delta chunks, then a
final ``done`` event with accumulated usage.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config.settings import Settings
from .base import LLMMessage, LLMResponse, LLMStreamEvent, LLMUsage, ModelCapabilities
from .capabilities import cached_detect

_log = logging.getLogger(__name__)

_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterLLMClient:
    """Async adapter over OpenRouter's OpenAI-compatible API."""

    name: str = "openrouter"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = settings.openrouter_default_model
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            api_key = self._settings.openrouter_api_key.get_secret_value()
            if not api_key:
                raise RuntimeError("OpenRouter selected but RABEEH_OPENROUTER_API_KEY is empty.")
            self._client = httpx.AsyncClient(
                base_url=_BASE_URL,
                timeout=self._settings.request_timeout_seconds,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "HTTP-Referer": "https://github.com/rabeeh/agent-pro",
                    "X-Title": "Rabeeh AI Agent Pro",
                },
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
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools

        try:
            resp = await client.post("/chat/completions", json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            _log.error("OpenRouter chat failed: %s", exc)
            raise

        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        content = choice.get("message", {}).get("content", "") or ""
        raw_usage = data.get("usage") or {}
        usage = LLMUsage(
            prompt_tokens=int(raw_usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(raw_usage.get("completion_tokens", 0) or 0),
        )
        usage.total_tokens = int(
            raw_usage.get("total_tokens", usage.prompt_tokens + usage.completion_tokens)
        )
        return LLMResponse(
            content=content,
            usage=usage,
            model=payload["model"],
            provider=self.name,
            raw=data,
            finish_reason=choice.get("finish_reason", "stop"),
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
        """Stream from OpenRouter using SSE."""
        client = await self._ensure_client()
        payload: dict[str, Any] = {
            "model": kwargs.get("model", self._model),
            "messages": [
                {"role": m.role, "content": m.content, **({"name": m.name} if m.name else {})}
                for m in messages
            ],
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools

        accumulated = ""
        finish_reason = "stop"
        usage = LLMUsage()
        tool_calls_acc: list[dict[str, Any]] = []

        try:
            async with client.stream("POST", "/chat/completions", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                    else:
                        continue

                    if data_str.strip() == "[DONE]":
                        break

                    import json as _json

                    try:
                        chunk = _json.loads(data_str)
                    except _json.JSONDecodeError:
                        continue

                    choices = chunk.get("choices", [])
                    if not choices:
                        # Usage may appear here on OpenRouter.
                        if "usage" in chunk:
                            u = chunk["usage"]
                            usage = LLMUsage(
                                prompt_tokens=int(u.get("prompt_tokens", 0) or 0),
                                completion_tokens=int(u.get("completion_tokens", 0) or 0),
                            )
                            usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
                        continue

                    delta = choices[0].get("delta", {})
                    if delta.get("content"):
                        accumulated += delta["content"]
                        yield LLMStreamEvent(
                            kind="chunk",
                            content=delta["content"],
                            model=chunk.get("model", payload["model"]),
                            provider=self.name,
                        )

                    # Tool calls (OpenAI format).
                    if delta.get("tool_calls"):
                        for tc in delta["tool_calls"]:
                            idx = tc.get("index", 0)
                            while len(tool_calls_acc) <= idx:
                                tool_calls_acc.append(
                                    {
                                        "id": "",
                                        "type": "function",
                                        "function": {"name": "", "arguments": ""},
                                    }
                                )
                            entry = tool_calls_acc[idx]
                            if tc.get("id"):
                                entry["id"] = tc["id"]
                            if tc.get("function"):
                                if tc["function"].get("name"):
                                    entry["function"]["name"] += tc["function"]["name"]
                                if tc["function"].get("arguments"):
                                    entry["function"]["arguments"] += tc["function"]["arguments"]

                    if choices[0].get("finish_reason"):
                        finish_reason = choices[0]["finish_reason"]

        except httpx.HTTPError as exc:
            yield LLMStreamEvent(
                kind="error",
                error=f"OpenRouter streaming failed: {exc}",
                model=payload["model"],
                provider=self.name,
            )
            return

        # Emit tool calls.
        for tc in tool_calls_acc:
            if tc.get("function", {}).get("name"):
                yield LLMStreamEvent(
                    kind="tool_call",
                    tool_calls=[tc],
                    model=payload["model"],
                    provider=self.name,
                )

        yield LLMStreamEvent(
            kind="done",
            content=accumulated,
            usage=usage,
            model=payload["model"],
            provider=self.name,
            finish_reason=finish_reason,
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def get_capabilities(self) -> ModelCapabilities:
        return cached_detect(self._model)
