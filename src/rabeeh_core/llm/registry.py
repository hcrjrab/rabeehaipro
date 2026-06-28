"""LLM client factory / process-wide registry.

Resolves ``Settings.default_provider`` to a concrete adapter. A single
client instance is cached per process because:

- HTTP connection pools are expensive to recreate.
- Providers (Ollama, OpenRouter, LiteLLM) are stateless across requests.

The registry also manages a shared ``LLMRouter`` instance for capability-aware
multi-provider orchestration.
"""

from __future__ import annotations

import logging
from typing import Literal

from ..config.settings import get_settings
from .base import LLMClient
from .mock import MockLLMClient
from .ollama import OllamaLLMClient
from .openrouter import OpenRouterLLMClient

_log = logging.getLogger(__name__)

ProviderName = Literal["ollama", "openrouter", "litellm", "mock"]

_client: LLMClient | None = None


def build_default_client(provider: ProviderName | None = None) -> LLMClient:
    """Construct a fresh client for the given (or configured) provider.

    Does NOT cache; callers wanting the shared instance should use
    :func:`get_client`. Exposed separately so tests can build isolated
    clients and so the router can spin up secondary providers.
    """
    settings = get_settings()
    name = provider or settings.default_provider
    _log.debug("Building LLM client for provider=%s", name)

    if name == "mock":
        return MockLLMClient(default_model="mock-1")
    if name == "ollama":
        return OllamaLLMClient(settings)
    if name == "openrouter":
        return OpenRouterLLMClient(settings)
    if name == "litellm":
        from .litellm_provider import LITELLM_ENABLED, LiteLLMProvider

        if not LITELLM_ENABLED:
            _log.warning(
                "provider=litellm requested but litellm is not installed; "
                "falling back to openrouter."
            )
            return OpenRouterLLMClient(settings)
        return LiteLLMProvider.from_settings(settings)
    raise ValueError(f"Unknown LLM provider: {name!r}")


def get_client() -> LLMClient:
    """Return the shared, cached LLM client for this process."""
    global _client
    if _client is None:
        _client = build_default_client()
    return _client


async def reset_client() -> None:
    """Close and clear the cached client (used by tests and on reload)."""
    global _client
    if _client is not None:
        try:
            await _client.close()
        except Exception:
            _log.debug("Error closing LLM client", exc_info=True)
    _client = None
