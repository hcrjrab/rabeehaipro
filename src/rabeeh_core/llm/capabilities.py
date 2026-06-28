"""Model capability detection and capability-aware routing logic.

Maps model identifiers to their known capabilities (vision, tools, context
length, etc.). Uses a curated registry for known models and heuristic
patterns for unknown ones.

The capability system lets the router answer questions like:
  "Which available provider can handle a vision task?"
  "Which model has the longest context for this large document?"
"""

from __future__ import annotations

import logging
import re

from .base import ModelCapabilities

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known-model registry
# ---------------------------------------------------------------------------
# Format: model_pattern -> ModelCapabilities
# Patterns are matched case-insensitively against the model string.

_KNOWN_MODELS: list[tuple[re.Pattern[str], ModelCapabilities]] = [
    # --- OpenAI ---
    (
        re.compile(r"gpt-4o"),
        ModelCapabilities(
            supports_vision=True,
            supports_tools=True,
            supports_structured_output=True,
            max_context_length=128000,
            max_output_tokens=16384,
        ),
    ),
    (
        re.compile(r"gpt-4(?!o).*turbo"),
        ModelCapabilities(
            supports_vision=True,
            supports_tools=True,
            max_context_length=128000,
            max_output_tokens=4096,
        ),
    ),
    (
        re.compile(r"gpt-4(?!o)"),
        ModelCapabilities(
            supports_tools=True,
            max_context_length=8192,
            max_output_tokens=4096,
        ),
    ),
    (
        re.compile(r"gpt-3\.5-turbo"),
        ModelCapabilities(
            supports_tools=True,
            max_context_length=16384,
            max_output_tokens=4096,
        ),
    ),
    (
        re.compile(r"o1"),
        ModelCapabilities(
            supports_vision=True,
            max_context_length=200000,
            max_output_tokens=100000,
            default_temperature=1.0,
        ),
    ),
    (
        re.compile(r"o3"),
        ModelCapabilities(
            supports_vision=True,
            supports_structured_output=True,
            max_context_length=200000,
            max_output_tokens=100000,
            default_temperature=1.0,
        ),
    ),
    # --- Anthropic ---
    (
        re.compile(r"claude-3\.5"),
        ModelCapabilities(
            supports_vision=True,
            supports_tools=True,
            supports_structured_output=True,
            max_context_length=200000,
            max_output_tokens=8192,
        ),
    ),
    (
        re.compile(r"claude-3"),
        ModelCapabilities(
            supports_vision=True,
            supports_tools=True,
            max_context_length=200000,
            max_output_tokens=4096,
        ),
    ),
    (
        re.compile(r"claude-4"),
        ModelCapabilities(
            supports_vision=True,
            supports_tools=True,
            supports_structured_output=True,
            max_context_length=200000,
            max_output_tokens=65536,
        ),
    ),
    (
        re.compile(r"claude-2"),
        ModelCapabilities(
            max_context_length=100000,
            max_output_tokens=4096,
        ),
    ),
    # --- Google ---
    (
        re.compile(r"gemini-2\.5"),
        ModelCapabilities(
            supports_vision=True,
            supports_tools=True,
            supports_structured_output=True,
            max_context_length=1048576,
            max_output_tokens=65536,
        ),
    ),
    (
        re.compile(r"gemini-2\.0"),
        ModelCapabilities(
            supports_vision=True,
            supports_tools=True,
            max_context_length=1048576,
            max_output_tokens=8192,
        ),
    ),
    (
        re.compile(r"gemini-1\.5"),
        ModelCapabilities(
            supports_vision=True,
            supports_tools=True,
            max_context_length=1048576,
            max_output_tokens=8192,
        ),
    ),
    # --- Meta Llama ---
    (
        re.compile(r"llama-?4"),
        ModelCapabilities(
            supports_tools=True,
            supports_structured_output=True,
            max_context_length=131072,
            max_output_tokens=4096,
        ),
    ),
    (
        re.compile(r"llama-?3\.\d+.*(?:70b|90b)"),
        ModelCapabilities(
            supports_tools=True,
            max_context_length=131072,
            max_output_tokens=4096,
        ),
    ),
    (
        re.compile(r"llama-?3\.\d+"),
        ModelCapabilities(
            supports_tools=True,
            max_context_length=8192,
            max_output_tokens=4096,
        ),
    ),
    (
        re.compile(r"llama-?2"),
        ModelCapabilities(
            max_context_length=4096,
            max_output_tokens=4096,
        ),
    ),
    # --- DeepSeek ---
    (
        re.compile(r"deepseek-(v3|r1)"),
        ModelCapabilities(
            supports_tools=True,
            max_context_length=65536,
            max_output_tokens=8192,
            default_temperature=0.0,
        ),
    ),
    (
        re.compile(r"deepseek-v2"),
        ModelCapabilities(
            supports_tools=True,
            max_context_length=128000,
            max_output_tokens=4096,
        ),
    ),
    (
        re.compile(r"deepseek-coder"),
        ModelCapabilities(
            supports_tools=True,
            max_context_length=16384,
            max_output_tokens=4096,
        ),
    ),
    # --- Qwen ---
    (
        re.compile(r"qwen-?2\.5.*(?:72b|32b)"),
        ModelCapabilities(
            supports_tools=True,
            max_context_length=131072,
            max_output_tokens=8192,
        ),
    ),
    (
        re.compile(r"qwen-?2\.5"),
        ModelCapabilities(
            supports_tools=True,
            max_context_length=32768,
            max_output_tokens=8192,
        ),
    ),
    (
        re.compile(r"qwen-?2"),
        ModelCapabilities(
            max_context_length=32768,
            max_output_tokens=4096,
        ),
    ),
    # --- Mistral ---
    (
        re.compile(r"mistral-large"),
        ModelCapabilities(
            supports_tools=True,
            supports_structured_output=True,
            max_context_length=128000,
            max_output_tokens=4096,
        ),
    ),
    (
        re.compile(r"mistral-small|ministral"),
        ModelCapabilities(
            supports_tools=True,
            max_context_length=128000,
            max_output_tokens=4096,
        ),
    ),
    (
        re.compile(r"mistral-?7b|mixtral"),
        ModelCapabilities(
            max_context_length=32768,
            max_output_tokens=4096,
        ),
    ),
    # --- Codestral / Codegen ---
    (
        re.compile(r"codestral"),
        ModelCapabilities(
            supports_tools=True,
            max_context_length=256000,
            max_output_tokens=8192,
        ),
    ),
    # --- Vision-specific models ---
    (
        re.compile(r"(?:llava|bakllava|cogvlm|idefics|fuyu)"),
        ModelCapabilities(
            supports_vision=True,
            max_context_length=4096,
            max_output_tokens=2048,
        ),
    ),
    # --- Default fallback for Ollama-style tags ---
    (
        re.compile(r".*:?latest$"),
        ModelCapabilities(
            supports_tools=False,
            max_context_length=4096,
            max_output_tokens=2048,
        ),
    ),
]


def detect_capabilities(model_id: str) -> ModelCapabilities:
    """Return the best-known capability descriptor for *model_id*.

    Iterates the known-model registry in priority order and returns the
    first match. If nothing matches, returns a conservative default.
    """
    for pattern, caps in _KNOWN_MODELS:
        if pattern.search(model_id.lower()):
            _log.debug("Capabilities matched %s -> %s", model_id, pattern.pattern)
            return caps

    _log.debug("No capability match for %s; using conservative defaults", model_id)
    return ModelCapabilities()


def detect_vision_capable(models: list[str]) -> bool:
    """Return ``True`` if any model in the list supports vision."""
    return any(detect_capabilities(m).supports_vision for m in models)


def detect_tool_capable(models: list[str]) -> bool:
    """Return ``True`` if any model in the list supports tool/function calling."""
    return any(detect_capabilities(m).supports_tools for m in models)


def best_model_for_task(
    models: list[str],
    *,
    needs_vision: bool = False,
    needs_tools: bool = False,
    needs_structured_output: bool = False,
    min_context: int = 0,
) -> str | None:
    """Select the best model from a list for a given task profile.

    Scores each model based on how well it satisfies the requirements,
    preferring models that meet *all* criteria, then the one with the
    longest context window.
    """
    scored: list[tuple[int, int, str]] = []

    for model_id in models:
        caps = detect_capabilities(model_id)
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
            # Does not meet minimum context requirement.
            continue

        scored.append((score, caps.max_context_length, model_id))

    if not scored:
        return None

    # Sort by score descending, then by context length descending for ties.
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return scored[0][2]


# ---------------------------------------------------------------------------
# Module-level cache for expensive lookups
# ---------------------------------------------------------------------------

_CAPABILITY_CACHE: dict[str, ModelCapabilities] = {}


def cached_detect(model_id: str) -> ModelCapabilities:
    """Cached version of :func:`detect_capabilities`."""
    if model_id not in _CAPABILITY_CACHE:
        _CAPABILITY_CACHE[model_id] = detect_capabilities(model_id)
    return _CAPABILITY_CACHE[model_id]


def clear_capability_cache() -> None:
    """Clear the capability cache (used in tests)."""
    _CAPABILITY_CACHE.clear()
