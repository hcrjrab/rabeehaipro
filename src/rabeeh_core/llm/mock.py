"""Deterministic in-process mock LLM client.

Used as the default provider so the application boots and all tests pass
without Ollama/OpenRouter being reachable. It is intentionally *useful*:

- Recognises a handful of structured prompts (planning, summarisation) and
  returns canned-but-shaped JSON, so the orchestrator loop is exercisable.
- Counts "tokens" as words for realistic usage numbers in tests.
- Exposes a ``responses`` queue for tests to script exact outputs.

This means Phase 2's planner/orchestrator can be developed and verified
end-to-end before any real model is wired in.
"""

from __future__ import annotations

import json
import re
from collections import deque
from typing import Any

from .base import (
    LLMMessage,
    LLMResponse,
    LLMStreamEvent,
    LLMUsage,
    ModelCapabilities,
)


def _count_tokens(text: str) -> int:
    """Cheap token estimate: ~words. Good enough for unit tests."""
    return max(1, len(re.findall(r"\S+", text)))


class MockLLMClient:
    """A scriptable, offline LLM stand-in implementing :class:`LLMClient`."""

    name: str = "mock"

    def __init__(self, default_model: str = "mock-1") -> None:
        self.default_model = default_model
        # Pre-seeded responses returned FIFO when non-empty; otherwise the
        # heuristic generator runs.
        self._scripted: deque[str] = deque()

    # -- test helpers -----------------------------------------------------
    def script(self, *responses: str) -> None:
        """Queue exact responses to return on the next ``chat`` calls."""
        self._scripted.extend(responses)

    # -- LLMClient protocol ----------------------------------------------
    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        # 1. Scripted response takes priority (deterministic tests).
        if self._scripted:
            content = self._scripted.popleft()
        else:
            content = self._generate(messages, tools=tools)

        prompt_text = " ".join(m.content for m in messages)
        usage = LLMUsage(
            prompt_tokens=_count_tokens(prompt_text),
            completion_tokens=_count_tokens(content),
        )
        usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
        return LLMResponse(
            content=content,
            usage=usage,
            model=self.default_model,
            provider=self.name,
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
        """Mock streaming: yields chunks then a done event."""
        full = await self.chat(
            messages, temperature=temperature, max_tokens=max_tokens, tools=tools
        )

        # Yield in ~20-char chunks.
        chunk_size = 20
        for i in range(0, len(full.content), chunk_size):
            yield LLMStreamEvent(
                kind="chunk",
                content=full.content[i : i + chunk_size],
                model=full.model,
                provider=self.name,
            )

        yield LLMStreamEvent(
            kind="done",
            content=full.content,
            usage=full.usage,
            model=full.model,
            provider=self.name,
            finish_reason=full.finish_reason,
        )

    async def close(self) -> None:
        """Nothing to release for the mock."""
        return None

    def get_capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            supports_vision=False,
            supports_tools=True,
            supports_streaming=True,
            supports_structured_output=True,
            max_context_length=8192,
            max_output_tokens=4096,
        )

    # -- heuristic generation --------------------------------------------
    def _generate(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> str:
        """Produce a context-aware canned response.

        The heuristics here are deliberately simple but *structured*: they
        return JSON when the prompt asks for a plan, so downstream parsing
        works without a real model.
        """
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"),
            "",
        )
        lowered = last_user.lower()

        # Plan request -> emit a minimal valid plan.
        if "plan" in lowered or "decompose" in lowered:
            plan = {
                "goal": last_user.strip()[:200],
                "steps": [
                    {
                        "description": "Understand the request and gather context.",
                        "assigned_agent": "research",
                        "tool_hints": ["web.search", "memory.recall"],
                        "expected_risk": "none",
                    },
                    {
                        "description": "Produce the requested artifact.",
                        "assigned_agent": "office",
                        "tool_hints": ["file.write"],
                        "expected_risk": "safe",
                    },
                    {
                        "description": "Review the output for correctness.",
                        "assigned_agent": "reviewer",
                        "tool_hints": [],
                        "expected_risk": "none",
                    },
                ],
                "notes": "Mock-generated default plan.",
            }
            return json.dumps(plan, ensure_ascii=False)

        # Summarisation request.
        if "summar" in lowered:
            sentences = re.split(r"(?<=[.!?])\s+", last_user)
            summary = " ".join(sentences[:2]) if sentences else "(nothing to summarise)"
            return f"Summary: {summary}"

        # Tool-calling request (very small stub).
        if tools:
            return json.dumps(
                {"tool": tools[0].get("function", {}).get("name", "unknown"), "arguments": {}},
                ensure_ascii=False,
            )

        # Fallback: echo with a marker so tests can assert presence.
        return f"[mock] Acknowledged: {last_user.strip()[:280]}"
