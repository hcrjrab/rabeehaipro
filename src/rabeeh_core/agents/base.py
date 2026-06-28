"""Abstract agent base class.

An *agent* is a stateless reasoning unit parameterised by:

- an :class:`LLMClient` (how it thinks),
- a registry of tools it *may* propose (what it can do),
- a short system prompt establishing its role/persona.

Agents return an :class:`AgentResult` containing either a finished message,
a tool call to be executed by the orchestrator, or a flag indicating the
sub-goal is complete. They never execute tools themselves.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from ..config.schemas import AgentMessage, AgentRole, ToolCallRequest
from ..llm.base import LLMClient, LLMMessage
from ..llm.registry import get_client

_log = logging.getLogger(__name__)


@dataclass(slots=True)
class AgentContext:
    """Per-invocation state handed to an agent.

    Carries the user's goal, the running conversation, and arbitrary
    scratchpad data (e.g. file paths, prior tool outputs) the orchestrator
    wants the agent to see.
    """

    task_id: UUID
    session_id: UUID
    goal: str
    history: list[AgentMessage] = field(default_factory=list)
    scratchpad: dict[str, Any] = field(default_factory=dict)

    def to_llm_messages(self, system_prompt: str) -> list[LLMMessage]:
        """Flatten conversation history into LLM-ready messages.

        Prepends a system message; preserves role + content order. Tool
        results (role ``"tool"``) are kept verbatim so the model sees them.
        """
        out: list[LLMMessage] = [LLMMessage(role="system", content=system_prompt)]
        for m in self.history:
            out.append(LLMMessage(role=m.role, content=m.content, name=m.name, metadata=m.metadata))
        return out


@dataclass(slots=True)
class AgentResult:
    """Structured outcome of one agent step.

    A result carries at least one of:

    - ``message``   -> text for the user / next agent (may coexist with the
                       other two: an agent narrating its action or final answer).
    - ``tool_call`` -> request the orchestrator execute a tool. Mutually
                       exclusive with ``done`` (you await the tool outcome first).
    - ``done``      -> this agent has nothing more to contribute to the step.
    """

    message: str | None = None
    tool_call: ToolCallRequest | None = None
    done: bool = False
    usage: dict[str, int] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Enforce the result-mode invariants.

        Rules
        -----
        - At least one of ``message`` / ``tool_call`` / ``done`` must be set.
        - ``tool_call`` and ``done`` are mutually exclusive: a step that
          proposes a tool is not finished (it awaits the tool's outcome).
        - ``message`` may accompany EITHER ``tool_call`` or ``done`` (an agent
          narrating its action / final answer). ``message`` alone is also fine.
        """
        has_message = self.message is not None
        has_tool = self.tool_call is not None
        if not (has_message or has_tool or self.done):
            raise ValueError("AgentResult must set message, tool_call, or done.")
        if has_tool and self.done:
            raise ValueError(
                "AgentResult cannot set both tool_call and done "
                "(await the tool outcome before finishing)."
            )


class BaseAgent(ABC):
    """Common base for every agent role.

    Subclasses implement :meth:`system_prompt` and :meth:`_run`. Everything
    else (logging, LLM injection, role identity) is shared.
    """

    role: AgentRole = AgentRole.PLANNER  # overridden by subclasses

    def __init__(self, llm: LLMClient | None = None) -> None:
        # Default to the shared client; tests inject a MockLLMClient.
        self.llm: LLMClient = llm or get_client()

    @property
    def name(self) -> str:
        """Human-friendly identifier derived from the role."""
        return f"{self.role.value}-agent"

    @abstractmethod
    def system_prompt(self) -> str:
        """Return the role-specific system prompt.

        Kept as a method (not a class attr) so prompts can reference config
        and be overridden cleanly by subclasses.
        """
        raise NotImplementedError

    @abstractmethod
    async def _run(self, ctx: AgentContext) -> AgentResult:
        """Role-specific reasoning step. Implemented by each agent."""
        raise NotImplementedError

    async def run(self, ctx: AgentContext) -> AgentResult:
        """Public entrypoint: log, delegate to ``_run``, log again."""
        _log.info("Agent %s step start (task=%s)", self.name, ctx.task_id)
        try:
            result = await self._run(ctx)
        except Exception:
            _log.exception("Agent %s raised on task %s", self.name, ctx.task_id)
            raise
        _log.info(
            "Agent %s step done (task=%s, done=%s, tool=%s)",
            self.name,
            ctx.task_id,
            result.done,
            result.tool_call.tool_name if result.tool_call else None,
        )
        return result


# ---------------------------------------------------------------------------
# Shared parsing helper (module-level for unit testing)
# ---------------------------------------------------------------------------
def _parse_action_json(
    raw: str,
    *,
    valid_actions: set[str],
    fallback: str,
) -> dict[str, Any]:
    """Parse an LLM action decision into a normalised dict.

    The shared contract every action-style agent uses is::

        {"action": "<one of valid_actions>", ...kwargs}

    This helper is tolerant of markdown fences and a trailing prose tail, but
    strict about the ``action`` field once the JSON is extracted. On any
    parse failure it returns ``{"action": fallback}`` so the caller can
    degrade gracefully (e.g. finish the step) rather than crash.
    """
    import json as _json
    import re as _re

    text = raw.strip()
    payload: dict[str, Any] | None = None
    try:
        payload = _json.loads(text)
    except _json.JSONDecodeError:
        fence = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, _re.DOTALL)
        if fence:
            try:
                payload = _json.loads(fence.group(1))
            except _json.JSONDecodeError:
                payload = None
        if payload is None:
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end > start:
                try:
                    payload = _json.loads(text[start : end + 1])
                except _json.JSONDecodeError:
                    payload = None

    if isinstance(payload, dict):
        action = str(payload.get("action", "")).lower().strip()
        if action in valid_actions:
            return payload
    return {"action": fallback}
