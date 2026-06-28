"""LLM provider abstraction.

Provides a single ``LLMClient`` Protocol and a registry of concrete
adapters (Ollama, OpenRouter, LiteLLM, Mock). Agents talk only to the
Protocol, never to a vendor SDK directly, so:

- Swapping providers is a config change, not a code change.
- Tests run against the in-process ``MockLLMClient`` (no network).
- The router (:class:`LLMRouter`) picks local-vs-cloud per call automatically
  with graceful failover and a circuit breaker.
- Model capabilities (vision, tools, context length) are auto-detected for
  intelligent task-to-model routing.
- Streaming is available through ``chat_stream()`` on every provider.
"""

from __future__ import annotations

from .base import (
    LLMClient,
    LLMMessage,
    LLMResponse,
    LLMStreamEvent,
    LLMUsage,
    ModelCapabilities,
)
from .capabilities import (
    best_model_for_task,
    cached_detect,
    clear_capability_cache,
    detect_capabilities,
    detect_tool_capable,
    detect_vision_capable,
)
from .litellm_provider import LITELLM_ENABLED, LiteLLMProvider
from .mock import MockLLMClient
from .registry import build_default_client, get_client
from .router import LLMRouter, build_router

__all__ = [
    "LITELLM_ENABLED",
    "LLMClient",
    "LLMMessage",
    "LLMResponse",
    "LLMRouter",
    "LLMStreamEvent",
    "LLMUsage",
    "LiteLLMProvider",
    "MockLLMClient",
    "ModelCapabilities",
    "best_model_for_task",
    "build_default_client",
    "build_router",
    "cached_detect",
    "clear_capability_cache",
    "detect_capabilities",
    "detect_tool_capable",
    "detect_vision_capable",
    "get_client",
]
