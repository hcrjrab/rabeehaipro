"""Planner agent.

Decomposes a goal into an ordered :class:`TaskPlan` of steps, each assigned
to an appropriate agent role. This is the *first* agent run in every task.

Design
------
- Uses a constrained JSON contract so the orchestrator can parse the plan
  deterministically (no free-form prose to wrangle).
- On malformed output, retries once with an explicit "you returned invalid
  JSON, fix it" nudge. Two failures fall back to a single-step plan rather
  than failing the whole task — resilience over rigidity.
- The system prompt enumerates available agent roles and tools so the model
  assigns work to roles that actually exist.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..config.schemas import AgentRole, RiskLevel, TaskPlan, TaskStep
from ..llm.base import LLMClient, LLMMessage
from .base import AgentContext, AgentResult, BaseAgent

_log = logging.getLogger(__name__)

# The JSON contract the model MUST return. Embedded verbatim in the prompt.
_PLAN_SCHEMA_HINT = """{
  "goal": "<the user's goal, restated>",
  "steps": [
    {
      "description": "<imperative, concrete action>",
      "assigned_agent": "<one of: research, coding, office, file, browser, vision, business, automation, reviewer, memory>",
      "tool_hints": ["<optional tool name>", "..."],
      "expected_risk": "<none | safe | destructive | elevated>"
    }
  ],
  "notes": "<optional caveats>"
}"""

_VALID_ROLES = ", ".join(r.value for r in AgentRole)


class PlannerAgent(BaseAgent):
    """LLM-driven goal decomposer producing a validated :class:`TaskPlan`."""

    role = AgentRole.PLANNER

    def __init__(self, llm: LLMClient | None = None, *, max_attempts: int = 2) -> None:
        super().__init__(llm=llm)
        self.max_attempts = max_attempts

    def system_prompt(self) -> str:
        """Establish the planner's role + output contract."""
        return (
            "You are the Planner of an autonomous AI agent system. "
            "Decompose the user's goal into a small ordered list of concrete steps. "
            f"Each step must be assigned to one of these agent roles: {_VALID_ROLES}. "
            "Prefer the FEWEST steps that fully achieve the goal; never pad. "
            "Respond with ONLY a JSON object matching exactly this schema, "
            "no markdown fences, no commentary:\n" + _PLAN_SCHEMA_HINT
        )

    async def _run(self, ctx: AgentContext) -> AgentResult:
        """Call the LLM and parse its response into a validated plan."""
        messages = ctx.to_llm_messages(self.system_prompt())
        messages.append(
            LLMMessage(
                role="user",
                content=f"Goal to plan: {ctx.goal}",
            )
        )

        last_error = ""
        for attempt in range(1, self.max_attempts + 1):
            if last_error:
                messages.append(
                    LLMMessage(
                        role="user",
                        content=(
                            f"Your previous response was invalid: {last_error}. "
                            "Return ONLY valid JSON matching the schema."
                        ),
                    )
                )
            response = await self.llm.chat(messages, temperature=0.1)
            try:
                plan = _parse_plan_json(response.content, ctx.goal)
            except _PlanParseError as exc:
                last_error = str(exc)
                _log.warning(
                    "Planner attempt %d/%d failed to parse: %s",
                    attempt,
                    self.max_attempts,
                    last_error,
                )
                continue
            _log.info("Planner produced %d-step plan.", len(plan.steps))
            return AgentResult(
                message=response.content,
                extra={"plan": plan.model_dump(), "attempts": attempt},
            )

        # Exhausted retries: degrade gracefully.
        _log.warning(
            "Planner fell back to a single-step plan after %d attempts.", self.max_attempts
        )
        fallback = TaskPlan(
            goal=ctx.goal,
            steps=[TaskStep(description=ctx.goal, assigned_agent=AgentRole.OFFICE)],
            notes="Fallback plan: model output could not be parsed.",
        )
        return AgentResult(
            message=json.dumps(fallback.model_dump(), default=str),
            extra={"plan": fallback.model_dump(), "fallback": True},
        )


# ---------------------------------------------------------------------------
# Parsing + validation (module-level for unit testing)
# ---------------------------------------------------------------------------
class _PlanParseError(ValueError):
    """Raised when the model output cannot be coerced into a valid plan."""


def _parse_plan_json(raw: str, goal: str) -> TaskPlan:
    """Parse + validate a planner JSON blob into a :class:`TaskPlan`.

    Tolerant of surrounding markdown fences (```` ```json ... ``` ````),
    a common model habit. Strict about structure once extracted.
    """
    payload = _extract_json(raw)
    if not isinstance(payload, dict):
        raise _PlanParseError("top-level JSON is not an object")

    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise _PlanParseError("'steps' must be a non-empty array")

    steps: list[TaskStep] = []
    for i, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, dict):
            raise _PlanParseError(f"step[{i}] is not an object")
        description = str(raw_step.get("description", "")).strip()
        if not description:
            raise _PlanParseError(f"step[{i}].description is empty")
        role = _coerce_role(raw_step.get("assigned_agent", "office"))
        steps.append(
            TaskStep(
                description=description,
                assigned_agent=role,
                tool_hints=[str(t) for t in raw_step.get("tool_hints", [])],
                expected_risk=_coerce_risk(raw_step.get("expected_risk", "none")),
            )
        )

    return TaskPlan(
        goal=str(payload.get("goal", goal)),
        steps=steps,
        notes=str(payload.get("notes", "")),
    )


def _coerce_role(value: Any) -> AgentRole:
    """Map free-form model strings to a valid :class:`AgentRole`."""
    if isinstance(value, AgentRole):
        return value
    try:
        return AgentRole(str(value))
    except ValueError:
        _log.debug("Unknown role %r; defaulting to office.", value)
        return AgentRole.OFFICE


def _coerce_risk(value: Any) -> RiskLevel:
    """Normalise risk strings to RiskLevel enum."""
    v = str(value).lower().strip()
    mapping = {
        "none": RiskLevel.NONE,
        "safe": RiskLevel.SAFE,
        "destructive": RiskLevel.DESTRUCTIVE,
        "elevated": RiskLevel.ELEVATED,
    }
    return mapping.get(v, RiskLevel.NONE)


def _extract_json(raw: str) -> Any:
    """Strip markdown fences and parse the inner JSON.

    Models sometimes wrap JSON in ``` ```json ... ``` ```. We try, in order:
    1. Direct ``json.loads``.
    2. Fence extraction via regex.
    3. Greedy first-``{``-to-last-``}`` slice as a last resort.
    """
    text = raw.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    import re

    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass

    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise _PlanParseError(f"could not parse JSON block: {exc}") from exc

    raise _PlanParseError("no JSON object found in response")
