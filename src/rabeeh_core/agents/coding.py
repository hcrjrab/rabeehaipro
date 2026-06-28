"""Coding agent.

Writes code via ``file.write`` and runs it via ``code.run``. It follows a
tight generate -> run -> observe -> fix loop:

1. Generate the initial code from the step description.
2. Write it to a file.
3. Run it.
4. If it fails, read the error and generate a fix (up to N retries).

The agent operates one tool-call per orchestrator step so the approval gate
can intercept ``code.run`` (DESTRUCTIVE). It uses the LLM for code generation
but the loop control is deterministic in the agent, not left to the model —
this prevents the model from "deciding" to skip testing.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config.schemas import AgentRole, RiskLevel, ToolCallRequest
from ..llm.base import LLMClient, LLMMessage
from .base import AgentContext, AgentResult, BaseAgent

_log = logging.getLogger(__name__)

_MAX_FIX_ATTEMPTS = 2


class CodingAgent(BaseAgent):
    """Code generator + runner with a bounded fix loop."""

    role = AgentRole.CODING

    def __init__(self, llm: LLMClient | None = None, *, max_fixes: int = _MAX_FIX_ATTEMPTS) -> None:
        super().__init__(llm=llm)
        self.max_fixes = max_fixes

    def system_prompt(self) -> str:
        return (
            "You are the Coding agent. You write clean, production-quality Python "
            "that solves the given task. Always: include type hints, handle errors, "
            "and print results to stdout. Respond with ONLY the code, no markdown "
            "fences, no commentary."
        )

    async def _run(self, ctx: AgentContext) -> AgentResult:
        """Decide the next coding action based on scratchpad state.

        State machine (driven by ``ctx.scratchpad['coding_phase']``):
        - ``generate``  -> LLM generates code -> file.write tool call.
        - ``run``       -> code.run tool call.
        - ``fix``       -> LLM regenerates with error context -> file.write.
        - ``done``      -> final summary.
        """
        phase = ctx.scratchpad.get("coding_phase", "generate")
        script_path = ctx.scratchpad.get("coding_script", f"generated/{ctx.task_id}.py")

        if phase == "generate":
            return await self._generate(ctx, script_path, error_context="")

        if phase == "run":
            return self._make_run_call(script_path)

        if phase == "fix":
            attempts = int(ctx.scratchpad.get("coding_fix_attempts", 0))
            if attempts >= self.max_fixes:
                return AgentResult(
                    message=f"Gave up after {attempts} fix attempts. Last error in tool results.",
                    done=True,
                )
            error = str(ctx.scratchpad.get("coding_last_error", ""))
            return await self._generate(ctx, script_path, error_context=error, is_fix=True)

        return AgentResult(message="Coding complete.", done=True)

    # ------------------------------------------------------------------
    # Phase implementations
    # ------------------------------------------------------------------
    async def _generate(
        self,
        ctx: AgentContext,
        script_path: str,
        *,
        error_context: str,
        is_fix: bool = False,
    ) -> AgentResult:
        """Ask the LLM for code (initial or fixed) and propose a file.write."""
        messages = ctx.to_llm_messages(self.system_prompt())
        prompt = f"Task: {ctx.scratchpad.get('step', ctx.goal)}"
        if is_fix and error_context:
            prompt += (
                f"\n\nThe previous version failed with this error:\n{error_context}\n"
                "Fix the bug and return the complete corrected script."
            )
        messages.append(LLMMessage(role="user", content=prompt))

        response = await self.llm.chat(messages, temperature=0.1)
        code = _strip_fences(response.content)

        next_phase = "run"
        ctx.scratchpad["coding_phase"] = next_phase
        ctx.scratchpad["coding_script"] = script_path

        return AgentResult(
            message=f"Writing {'fixed ' if is_fix else ''}script to {script_path}",
            tool_call=ToolCallRequest(
                tool_name="file.write",
                arguments={"path": script_path, "content": code},
                risk=RiskLevel.SAFE,
                rationale="Write generated script before running it.",
            ),
        )

    def _make_run_call(self, script_path: str) -> AgentResult:
        """Propose running the generated script."""
        return AgentResult(
            message=f"Running {script_path}",
            tool_call=ToolCallRequest(
                tool_name="code.run",
                arguments={"path": script_path, "timeout": 30},
                risk=RiskLevel.DESTRUCTIVE,
                rationale="Execute the generated script to verify correctness.",
            ),
        )


# The orchestrator, after a code.run result, inspects the outcome and sets
# the next phase. This helper is exposed so the runner/graph can call it
# without duplicating the logic. It is intentionally pure (no LLM calls).
def classify_run_result(run_result_data: dict[str, Any]) -> str:
    """Return the next coding phase from a ``code.run`` tool result.

    - exit_code 0  -> 'done' (success).
    - non-zero     -> 'fix' (retry generation with the error).
    """
    exit_code = int(run_result_data.get("exit_code", -1))
    return "done" if exit_code == 0 else "fix"


def _strip_fences(text: str) -> str:
    """Remove markdown code fences if the model wrapped the code."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Drop the opening fence (and optional language tag).
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        # Drop the closing fence.
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip() + "\n"
