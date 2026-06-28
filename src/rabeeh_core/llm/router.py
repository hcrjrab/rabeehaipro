"""Resilient LLM router: local-first with graceful cloud fallback.

The router is itself an :class:`LLMClient`. It holds an ordered chain of
providers and, on each call:

1. Tries the primary (local Ollama) for low latency + privacy.
2. On failure (timeout, 5xx, connection error) transparently retries the
   next provider, logging the failover.
3. Tracks per-provider health so a repeatedly-failing provider is
   *circuit-broken* for a cooldown window rather than retried every call.

Capability-aware routing
------------------------
The ``select_for_task`` method picks the best provider based on model
capabilities (vision, tools, context length) rather than always trying
providers in a fixed order. Useful when a task explicitly needs vision or
a large context window.

Streaming
---------
``chat_stream`` is transparently passed through to the first healthy hop
that supports streaming.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from .base import LLMClient, LLMMessage, LLMResponse, LLMStreamEvent

_log = logging.getLogger(__name__)


@dataclass(slots=True)
class _ProviderHealth:
    """Rolling health record used by the circuit-breaker.

    - ``consecutive_failures`` counts failures; reaching ``failure_threshold``
      opens the circuit.
    - ``opened_at`` is the epoch second the circuit opened; we re-allow a
      *probe* call after ``cooldown_seconds``.
    """

    consecutive_failures: int = 0
    opened_at: float | None = None
    last_success_at: float | None = None
    total_calls: int = 0
    total_failures: int = 0


@dataclass
class _RouteHop:
    """A provider entry in the router chain with its health bookkeeping."""

    client: LLMClient
    role: str  # "local" | "cloud" | "mock"
    health: _ProviderHealth = field(default_factory=_ProviderHealth)


class LLMRouter:
    """An :class:`LLMClient` that fails over across a provider chain.

    Construct via :func:`build_router` (which reads settings) rather than
    directly, so the chain reflects configuration. Tests can build a custom
    chain by passing hand-made hops.
    """

    def __init__(
        self,
        hops: list[_RouteHop],
        *,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
    ) -> None:
        if not hops:
            raise ValueError("LLMRouter requires at least one provider hop.")
        self._hops = hops
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds

    @property
    def name(self) -> str:
        """Composite name reflecting the whole chain."""
        return "router[" + "->".join(f"{h.role}:{h.client.name}" for h in self._hops) + "]"

    # ------------------------------------------------------------------
    # Capability-aware selection
    # ------------------------------------------------------------------

    def select_for_task(
        self,
        *,
        needs_vision: bool = False,
        needs_tools: bool = False,
        needs_structured_output: bool = False,
        min_context: int = 0,
    ) -> LLMClient | None:
        """Select the best available (healthy) provider for a task profile.

        Returns ``None`` if no healthy provider meets the requirements.
        """
        available: list[str] = []
        now = time.monotonic()
        for hop in self._hops:
            if self._is_open(hop, now):
                continue
            caps = hop.client.get_capabilities()
            available.append(
                f"{hop.client.name}::{caps.supports_vision}::{caps.supports_tools}::{caps.max_context_length}"
            )

        if not available:
            return None

        # Build a flat list of (model_id, hop) pairs.
        candidates: list[tuple[str, _RouteHop]] = []
        for hop in self._hops:
            if self._is_open(hop, now):
                continue
            caps = hop.client.get_capabilities()
            model_id = f"{hop.client.name}-model"
            candidates.append((model_id, hop))

        # Score hop.client.name using capability detection on known patterns.
        scored: list[tuple[int, int, _RouteHop]] = []
        for _model_id, hop in candidates:
            caps = hop.client.get_capabilities()
            score = 0
            if needs_vision and caps.supports_vision:
                score += 100
            if needs_tools and caps.supports_tools:
                score += 100
            if needs_structured_output and caps.supports_structured_output:
                score += 100
            if caps.max_context_length >= min_context:
                score += 50
            else:
                continue
            scored.append((score, caps.max_context_length, hop))

        if not scored:
            return None

        scored.sort(key=lambda x: (-x[0], -x[1]))
        return scored[0][2].client

    # ------------------------------------------------------------------
    # Circuit-breaker helpers
    # ------------------------------------------------------------------
    def _is_open(self, hop: _RouteHop, now: float) -> bool:
        """True if the circuit is open AND cooldown hasn't elapsed."""
        if hop.health.opened_at is None:
            return False
        if now - hop.health.opened_at >= self.cooldown_seconds:
            _log.debug("Circuit half-open for %s; probing.", hop.client.name)
            hop.health.opened_at = None
            return False
        return True

    def _record_success(self, hop: _RouteHop, now: float) -> None:
        h = hop.health
        h.consecutive_failures = 0
        h.opened_at = None
        h.last_success_at = now
        h.total_calls += 1

    def _record_failure(self, hop: _RouteHop, now: float) -> None:
        h = hop.health
        h.consecutive_failures += 1
        h.total_calls += 1
        h.total_failures += 1
        if h.consecutive_failures >= self.failure_threshold and h.opened_at is None:
            h.opened_at = now
            _log.warning(
                "Circuit opened for provider %s after %d failures.",
                hop.client.name,
                h.consecutive_failures,
            )

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
        """Try each provider in order until one succeeds.

        Raises the last error only if *every* provider fails.
        """
        now = time.monotonic()
        last_error: Exception | None = None

        for hop in self._hops:
            if self._is_open(hop, now):
                _log.debug("Skipping %s (circuit open).", hop.client.name)
                continue
            try:
                response = await hop.client.chat(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    **kwargs,
                )
            except Exception as exc:
                last_error = exc
                self._record_failure(hop, time.monotonic())
                _log.warning("Provider %s failed (%s); failing over.", hop.client.name, exc)
                continue

            if not response.ok:
                last_error = RuntimeError(f"{hop.client.name} returned empty content.")
                self._record_failure(hop, time.monotonic())
                continue

            self._record_success(hop, time.monotonic())
            response.provider = hop.client.name
            return response

        raise RuntimeError(
            f"All {len(self._hops)} LLM providers failed. Last error: {last_error}"
        ) from last_error

    async def chat_stream(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamEvent]:
        """Stream from the first healthy provider that supports streaming."""
        now = time.monotonic()
        last_error: str | None = None

        for hop in self._hops:
            if self._is_open(hop, now):
                _log.debug("Skipping %s (circuit open).", hop.client.name)
                continue
            try:
                caps = hop.client.get_capabilities()
                if not caps.supports_streaming:
                    _log.debug("Provider %s does not support streaming; skipping.", hop.client.name)
                    continue

                stream = hop.client.chat_stream(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    **kwargs,
                )
                # Pass through events, annotating provider.
                async for event in stream:
                    if not event.provider:
                        event.provider = hop.client.name
                    yield event
                    if event.kind == "done":
                        self._record_success(hop, time.monotonic())
                        return
                    if event.kind == "error":
                        last_error = event.error
                        self._record_failure(hop, time.monotonic())
                        break
                else:
                    # Stream exhausted without done/error.
                    self._record_success(hop, time.monotonic())
                    return

            except Exception as exc:
                last_error = str(exc)
                self._record_failure(hop, time.monotonic())
                _log.warning(
                    "Provider %s streaming failed (%s); failing over.", hop.client.name, exc
                )
                continue

        # All hops exhausted.
        yield LLMStreamEvent(
            kind="error",
            error=f"All {len(self._hops)} providers failed streaming. Last error: {last_error}",
        )

    async def close(self) -> None:
        """Close every underlying client in the chain."""
        for hop in self._hops:
            try:
                await hop.client.close()
            except Exception:
                _log.debug("Error closing provider %s", hop.client.name, exc_info=True)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def health_report(self) -> list[dict[str, Any]]:
        """Snapshot of per-provider health (for the ``/readyz`` / metrics)."""
        return [
            {
                "role": hop.role,
                "provider": hop.client.name,
                "consecutive_failures": hop.health.consecutive_failures,
                "total_calls": hop.health.total_calls,
                "total_failures": hop.health.total_failures,
                "circuit_open": hop.health.opened_at is not None,
                "last_success_at": hop.health.last_success_at,
            }
            for hop in self._hops
        ]

    def capabilities_report(self) -> list[dict[str, Any]]:
        """Per-provider capability descriptor (for debug UIs)."""
        return [
            {
                "role": hop.role,
                "provider": hop.client.name,
                "capabilities": {
                    "supports_vision": caps.supports_vision,
                    "supports_tools": caps.supports_tools,
                    "supports_streaming": caps.supports_streaming,
                    "max_context_length": caps.max_context_length,
                    "max_output_tokens": caps.max_output_tokens,
                },
            }
            for hop in self._hops
            for caps in [hop.client.get_capabilities()]
        ]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def build_router() -> LLMRouter:
    """Build a router chain from settings.

    Strategy (``prefer_local=True``, the default):
        litellm (if key set) / ollama -> openrouter (if key set) -> mock

    With ``prefer_local=False`` the order flips so cloud is primary. The
    mock hop is always appended as a last-resort guarantee that the router
    *never* raises "no providers" — useful in dev/CI.
    """
    from ..config.settings import get_settings
    from .mock import MockLLMClient
    from .ollama import OllamaLLMClient
    from .openrouter import OpenRouterLLMClient

    settings = get_settings()
    hops: list[_RouteHop] = []

    def _add(client: LLMClient, role: str) -> None:
        hops.append(_RouteHop(client=client, role=role))

    or_key = settings.openrouter_api_key.get_secret_value()
    litellm_key = settings.litellm_api_key.get_secret_value() if settings.litellm_api_key else ""

    if settings.default_provider == "mock":
        _add(MockLLMClient(default_model="mock-1"), "mock")
        return LLMRouter(hops)

    # --- Primary tier ---
    if settings.prefer_local:
        if settings.litellm_enabled and litellm_key:
            from .litellm_provider import LiteLLMProvider

            _add(LiteLLMProvider.from_settings(settings), "cloud")
        else:
            _add(OllamaLLMClient(settings), "local")
        if or_key:
            _add(OpenRouterLLMClient(settings), "cloud")
    else:
        if or_key:
            _add(OpenRouterLLMClient(settings), "cloud")
        if settings.litellm_enabled and litellm_key:
            from .litellm_provider import LiteLLMProvider

            _add(LiteLLMProvider.from_settings(settings), "cloud")
        else:
            _add(OllamaLLMClient(settings), "local")

    # Safety net.
    _add(MockLLMClient(default_model="mock-fallback"), "mock")

    _log.info(
        "LLM router chain: %s",
        " -> ".join(f"{h.role}:{h.client.name}" for h in hops),
    )
    return LLMRouter(hops)
