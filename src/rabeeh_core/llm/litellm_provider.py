"""LiteLLM provider adapter.

LiteLLM provides a unified interface to 100+ LLM providers (OpenAI,
Anthropic, Google, Ollama, AWS Bedrock, Azure, Together AI, etc.) through a
single SDK. This adapter wraps it behind the ``LLMClient`` Protocol so the
rest of the system is provider-agnostic.

Key features
------------
- Single adapter for all LiteLLM-supported providers.
- Streaming via ``chat_stream`` using LiteLLM's ``acompletion`` with
  ``stream=True``.
- Automatic model string routing (e.g. ``"anthropic/claude-4"`` or just
  ``"gpt-4o"``).
- Provider-specific configuration via ``litellm`` params dictionary.

The ``LITELLM_ENABLED`` flag lets the app degrade gracefully when the
optional ``litellm`` package is not installed.
"""

from __future__ import annotations

import logging
from typing import Any

from .base import (
    LLMMessage,
    LLMResponse,
    LLMStreamEvent,
    LLMUsage,
    ModelCapabilities,
)
from .capabilities import cached_detect

_log = logging.getLogger(__name__)

# Guard: litellm is an optional extra.
try:
    import litellm
    from litellm import acompletion, supports_function_calling

    LITELLM_ENABLED = True
except ImportError:  # pragma: no cover
    LITELLM_ENABLED = False
    _log.warning("litellm not installed; LiteLLM provider unavailable.")
    acompletion = None
    supports_function_calling = None


class LiteLLMProvider:
    """Adapter wrapping LiteLLM's ``acompletion`` behind ``LLMClient``.

    Usage::

        provider = LiteLLMProvider(model="gpt-4o", api_key=os.getenv("OPENAI_API_KEY"))
        resp = await provider.chat([LLMMessage(role="user", content="Hello")])
    """

    name: str = "litellm"

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        api_base: str | None = None,
        max_retries: int = 2,
        litellm_params: dict[str, Any] | None = None,
    ) -> None:
        if not LITELLM_ENABLED:
            raise RuntimeError(
                "LiteLLM is not installed. Install with: pip install 'rabeeh-core[litellm]'"
            )

        self._model = model
        self._api_key = api_key
        self._api_base = api_base
        self._max_retries = max_retries
        self._litellm_params = litellm_params or {}
        self._closed = False

        # Suppress LiteLLM's own verbose logging by default.
        litellm.set_verbose = False

    # ------------------------------------------------------------------
    # LLMClient protocol
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        if self._closed:
            raise RuntimeError("LiteLLM provider has been closed.")

        response = await acompletion(
            model=self._resolve_model(kwargs),
            messages=[self._to_dict(m) for m in messages],
            temperature=temperature,
            max_tokens=max_tokens or None,
            tools=tools or None,
            stream=False,
            api_key=self._api_key,
            api_base=self._api_base,
            num_retries=self._max_retries,
            **self._litellm_params,
        )

        choice = response.choices[0]
        content = choice.message.content or ""
        raw_usage = getattr(response, "usage", None)
        usage = LLMUsage(
            prompt_tokens=getattr(raw_usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(raw_usage, "completion_tokens", 0) or 0,
        )
        total = getattr(raw_usage, "total_tokens", 0) or 0
        usage.total_tokens = total or (usage.prompt_tokens + usage.completion_tokens)

        return LLMResponse(
            content=content,
            usage=usage,
            model=response.model,
            provider=self.name,
            raw=response.model_dump() if hasattr(response, "model_dump") else None,
            finish_reason=getattr(choice, "finish_reason", "stop") or "stop",
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
        if self._closed:
            raise RuntimeError("LiteLLM provider has been closed.")

        response = await acompletion(
            model=self._resolve_model(kwargs),
            messages=[self._to_dict(m) for m in messages],
            temperature=temperature,
            max_tokens=max_tokens or None,
            tools=tools or None,
            stream=True,
            api_key=self._api_key,
            api_base=self._api_base,
            num_retries=self._max_retries,
            **self._litellm_params,
        )

        accumulated = ""
        usage = LLMUsage()
        finish_reason = "stop"
        tool_calls_acc: list[dict[str, Any]] = []

        async for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            # Text delta.
            if delta.content:
                accumulated += delta.content
                yield LLMStreamEvent(
                    kind="chunk",
                    content=delta.content,
                    model=chunk.model,
                    provider=self.name,
                )

            # Tool call fragments.
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    # Accumulate partial tool calls.
                    if tc.index is not None:
                        while len(tool_calls_acc) <= tc.index:
                            tool_calls_acc.append(
                                {
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                }
                            )
                        entry = tool_calls_acc[tc.index]
                        if tc.id:
                            entry["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                entry["function"]["name"] += tc.function.name
                            if tc.function.arguments:
                                entry["function"]["arguments"] += tc.function.arguments

            # Finish reason.
            if chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason

            # Usage in final chunk.
            if hasattr(chunk, "usage") and chunk.usage:
                usage = LLMUsage(
                    prompt_tokens=getattr(chunk.usage, "prompt_tokens", 0) or 0,
                    completion_tokens=getattr(chunk.usage, "completion_tokens", 0) or 0,
                )
                usage.total_tokens = usage.prompt_tokens + usage.completion_tokens

        # Emit tool calls if any.
        for tc in tool_calls_acc:
            if tc.get("function", {}).get("name"):
                yield LLMStreamEvent(
                    kind="tool_call",
                    tool_calls=[tc],
                    model=response.model if hasattr(response, "model") else "",
                    provider=self.name,
                )

        yield LLMStreamEvent(
            kind="done",
            content=accumulated,
            usage=usage,
            model=response.model if hasattr(response, "model") else "",
            provider=self.name,
            finish_reason=finish_reason,
        )

    async def close(self) -> None:
        self._closed = True

    def get_capabilities(self) -> ModelCapabilities:
        return cached_detect(self._model)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_model(self, kwargs: dict[str, Any]) -> str:
        return str(kwargs.get("model", self._model))

    @staticmethod
    def _to_dict(msg: LLMMessage) -> dict[str, Any]:
        d: dict[str, Any] = {"role": msg.role, "content": msg.content}
        if msg.name:
            d["name"] = msg.name
        return d

    @classmethod
    def from_settings(cls, settings: Any) -> LiteLLMProvider:
        """Factory from the project's ``Settings`` object."""
        api_key = None
        if settings.litellm_api_key:
            api_key = settings.litellm_api_key.get_secret_value()

        return cls(
            model=settings.litellm_default_model,
            api_key=api_key,
            api_base=settings.litellm_api_base or None,
            litellm_params={
                "fallbacks": [settings.litellm_fallback_model],
                "max_retries": settings.litellm_max_retries,
            },
        )
