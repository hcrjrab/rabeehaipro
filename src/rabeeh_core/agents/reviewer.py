"""Reviewer agent.

Runs after each execution step (or at the end) to validate correctness. It
is the system's quality gate: rather than trusting the model's self-report,
the reviewer independently checks whether the step achieved its aim using
the evidence in the conversation/tool results.

Outputs a structured verdict via JSON:
    {"verdict": "pass" | "fail" | "replan", "reason": "...", "fix_hint": "..."}

- ``pass``    -> step accepted, move on.
- ``fail``    -> step failed; orchestrator records the error.
- ``replan``  -> the plan itself was wrong; orchestrator loops back to the
                 planner with the reviewer's fix_hint.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ..config.schemas import AgentRole
from ..llm.base import LLMClient, LLMMessage
from .base import AgentContext, AgentResult, BaseAgent

_log = logging.getLogger(__name__)

_REVIEW_SCHEMA_HINT = """{
  "verdict": "<pass | fail | replan>",
  "reason": "<one sentence>",
  "fix_hint": "<what to change, if verdict != pass>"
}"""

_RE_VERDICT = re.compile(r'"verdict"\s*:\s*"([^"]+)"')


class ReviewerAgent(BaseAgent):
    """Quality-gate agent that validates step outputs."""

    role = AgentRole.REVIEWER

    def __init__(self, llm: LLMClient | None = None, *, max_attempts: int = 2) -> None:
        super().__init__(llm=llm)
        self.max_attempts = max_attempts

    def system_prompt(self) -> str:
        return (
            "You are the Reviewer of an autonomous AI agent system. "
            "Given the goal, the executed step, and the tool results, decide "
            "whether the step achieved its aim. Be strict but fair: only pass "
            "when there is concrete evidence of success. "
            "Respond with ONLY a JSON object matching this schema:\n" + _REVIEW_SCHEMA_HINT
        )

    async def _run(self, ctx: AgentContext) -> AgentResult:
        """Ask the model to review the latest step and parse its verdict."""
        step_desc = str(ctx.scratchpad.get("step", "(no step description)"))
        # Surface the most recent tool results as evidence for the review.
        evidence = ctx.scratchpad.get("tool_results", [])

        messages = ctx.to_llm_messages(self.system_prompt())
        messages.append(
            LLMMessage(
                role="user",
                content=(
                    f"Goal: {ctx.goal}\n"
                    f"Step under review: {step_desc}\n"
                    f"Evidence (tool results): {json.dumps(evidence, default=str)[:2000]}"
                ),
            )
        )

        last_error = ""
        for _attempt in range(1, self.max_attempts + 1):
            if last_error:
                messages.append(
                    LLMMessage(
                        role="user",
                        content=(
                            f"Previous response invalid ({last_error}). "
                            "Return ONLY JSON with a 'verdict' of pass|fail|replan."
                        ),
                    )
                )
            response = await self.llm.chat(messages, temperature=0.0)
            verdict, reason, fix_hint = _parse_review(response.content)
            if verdict is not None:
                _log.info("Reviewer verdict=%s (%s)", verdict, reason)
                return AgentResult(
                    message=response.content,
                    extra={"verdict": verdict, "reason": reason, "fix_hint": fix_hint},
                    done=(verdict == "pass"),
                )
            last_error = reason  # reason holds the parse error here

        # Default to 'fail' if the model couldn't be coerced into a verdict.
        _log.warning("Reviewer could not parse a verdict; defaulting to fail.")
        return AgentResult(
            message="",
            extra={"verdict": "fail", "reason": "unparseable review output", "fix_hint": ""},
            done=False,
        )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def _parse_review(raw: str) -> tuple[str | None, str, str]:
    """Extract (verdict, reason, fix_hint) from a reviewer response.

    Returns ``(None, parse_error, "")`` on failure so the caller can retry.
    """
    payload: dict[str, Any] | None = None
    try:
        payload = json.loads(raw.strip())
    except json.JSONDecodeError:
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if fence:
            try:
                payload = json.loads(fence.group(1))
            except json.JSONDecodeError:
                payload = None

    if payload and isinstance(payload.get("verdict"), str):
        verdict = payload["verdict"].lower().strip()
        if verdict in {"pass", "fail", "replan"}:
            return (
                verdict,
                str(payload.get("reason", "")),
                str(payload.get("fix_hint", "")),
            )

    # Fallback: regex-scan for a verdict token (robust to prose wrapping).
    match = _RE_VERDICT.search(raw)
    if match and match.group(1) in {"pass", "fail", "replan"}:
        return match.group(1), "extracted via regex", ""

    return None, "no valid verdict found", ""
