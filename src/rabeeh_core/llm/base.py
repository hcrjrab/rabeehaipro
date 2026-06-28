"""LLM client Protocol + shared dataclasses.

A *Protocol* (structural typing) is used instead of an ABC so providers stay
decoupled: any object with the right methods qualifies, including mocks
defined in test modules without inheriting from anything.

All methods are ``async`` because providers are I/O bound (HTTP) and the
orchestrator runs them concurrently via ``asyncio``. Sync adapters (rare)
should wrap themselves with ``asyncio.to_thread``.

Streaming
---------
Providers expose ``chat_stream`` which yields ``LLMStreamEvent`` objects.
The orchestrator / WebSocket relay can consume these incrementally rather
than waiting for the full response.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Message / response types
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class LLMMessage:
    """One chat message. Roles mirror OpenAI's chat schema for portability."""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LLMUsage:
    """Token accounting for cost/observability.

    Providers that don't report tokens (some local models) return zeros;
    the cost calculator treats missing data as ``0`` rather than failing.
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: LLMUsage) -> LLMUsage:
        """Combine two usage records (used when aggregating sub-calls)."""
        return LLMUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


@dataclass(slots=True)
class LLMResponse:
    """Normalised response from any provider."""

    content: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    model: str = ""
    provider: str = ""
    raw: Any = None  # provider-specific payload for debugging
    finish_reason: str = "stop"

    @property
    def ok(self) -> bool:
        """A response is "ok" if it produced non-empty text."""
        return bool(self.content)


# ---------------------------------------------------------------------------
# Streaming types
# ---------------------------------------------------------------------------

StreamEventKind = Literal["chunk", "tool_call", "done", "error"]


@dataclass(slots=True)
class LLMStreamEvent:
    """One event yielded during a streaming LLM call.

    ``chunk``    -> partial text delta (concatenate on the client).
    ``tool_call`` -> a complete tool-call fragment (when using function calling).
    ``done``     -> final event with accumulated usage & full content.
    ``error``    -> irrecoverable error; streaming has terminated.
    """

    kind: StreamEventKind
    content: str = ""
    usage: LLMUsage | None = None
    tool_calls: list[dict[str, Any]] | None = None
    model: str = ""
    provider: str = ""
    error: str | None = None
    finish_reason: str = ""


# ---------------------------------------------------------------------------
# Model capability descriptors
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class ModelCapabilities:
    """Describes what a given model can do.

    Used by the capability-aware router to match tasks to the best provider.
    """

    supports_vision: bool = False
    supports_tools: bool = False
    supports_streaming: bool = True
    supports_structured_output: bool = False
    max_context_length: int = 8192
    max_output_tokens: int = 4096
    default_temperature: float = 0.2


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMClient(Protocol):
    """Structural interface every provider adapter must satisfy."""

    @property
    def name(self) -> str: ...

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a complete (non-streaming) completion."""
        ...

    async def chat_stream(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamEvent]:
        """Stream tokens / events as they arrive.

        Default implementation yields a single ``done`` event built from the
        non-streaming ``chat()`` result, so providers that don't implement
        streaming still produce a valid (synchronous) stream.
        """
        response = await self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            **kwargs,
        )
        yield LLMStreamEvent(
            kind="done",
            content=response.content,
            usage=response.usage,
            model=response.model,
            provider=response.provider,
            finish_reason=response.finish_reason,
        )

    async def close(self) -> None:
        """Release any underlying resources (HTTP clients, sockets)."""
        ...

    def get_capabilities(self) -> ModelCapabilities:
        """Return the static capability descriptor for this provider."""
        return ModelCapabilities()
