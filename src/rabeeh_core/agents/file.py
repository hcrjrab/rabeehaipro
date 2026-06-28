"""File agent.

Operates on the workspace filesystem: explores, reads, writes, copies, moves
and deletes files. It follows an **observe -> decide -> act** loop driven by
a state machine in the scratchpad:

1. ``explore``  -> list the workspace (or a subdir) so the agent knows what's there.
2. ``decide``   -> ask the LLM what to do next given the listing + goal.
3. ``act``      -> execute the chosen tool (read/write/copy/move/delete).
4. ``done``     -> final summary.

The first step is *always* an exploration (read-only, NONE risk) so the agent
never blindly writes over existing work. Deletions/moves are proposed at
``DESTRUCTIVE`` risk so the approval gate intercepts them.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config.schemas import AgentRole, RiskLevel, ToolCallRequest
from ..llm.base import LLMMessage
from .base import AgentContext, AgentResult, BaseAgent, _parse_action_json

_log = logging.getLogger(__name__)

# Maps the LLM's action verb -> (tool_name, risk).
_ACTION_TO_TOOL: dict[str, tuple[str, RiskLevel]] = {
    "list": ("file.list", RiskLevel.NONE),
    "read": ("file.read", RiskLevel.NONE),
    "write": ("file.write", RiskLevel.SAFE),
    "copy": ("file.copy", RiskLevel.SAFE),
    "move": ("file.move", RiskLevel.DESTRUCTIVE),
    "delete": ("file.delete", RiskLevel.DESTRUCTIVE),
    "done": ("", RiskLevel.NONE),
}

_VALID_ACTIONS = set(_ACTION_TO_TOOL)


class FileAgent(BaseAgent):
    """Workspace filesystem operator (observe -> decide -> act)."""

    role = AgentRole.FILE

    def __init__(self, *, max_steps: int = 6) -> None:
        # FileAgent uses the shared client from BaseAgent by default; no LLM
        # call is needed for the deterministic explore phase.
        super().__init__()
        self.max_steps = max_steps

    def system_prompt(self) -> str:
        return (
            "You are the File agent. You manage files inside the agent workspace: "
            "list, read, write, copy, move and delete them. Always explore first "
            "to avoid clobbering existing files. Respond with ONLY a JSON object "
            "matching exactly this schema, no markdown fences, no commentary:\n"
            "{\n"
            '  "action": "<list | read | write | copy | move | delete | done>",\n'
            '  "path": "<relative path>",\n'
            '  "content": "<text>",       // write only\n'
            '  "source": "<src path>",    // copy/move only\n'
            '  "destination": "<dst path>" // copy/move only\n'
            "}"
        )

    async def _run(self, ctx: AgentContext) -> AgentResult:
        """Drive the explore -> decide -> act state machine one step at a time."""
        phase = ctx.scratchpad.get("file_phase", "explore")
        step_no = int(ctx.scratchpad.get("file_step", 0))

        # Step 1: explore the workspace (always read-only first).
        if phase == "explore":
            return self._explore(ctx, step_no)

        # Over-budget guard: force completion to avoid an infinite loop.
        if step_no >= self.max_steps:
            return AgentResult(
                message=f"File operations complete (max {self.max_steps} steps reached).",
                done=True,
            )

        # Step 2+: ask the LLM what to do next.
        ctx.scratchpad["file_step"] = step_no + 1
        return await self._decide(ctx)

    # ------------------------------------------------------------------
    # Phases
    # ------------------------------------------------------------------
    def _explore(self, ctx: AgentContext, step_no: int) -> AgentResult:
        """Propose a read-only directory listing to orient the agent."""
        ctx.scratchpad["file_phase"] = "decide"
        ctx.scratchpad["file_step"] = step_no + 1
        return AgentResult(
            message="Listing workspace contents before acting.",
            tool_call=ToolCallRequest(
                tool_name="file.list",
                arguments={"path": ""},
                risk=RiskLevel.NONE,
                rationale="Explore the workspace before any file operation.",
            ),
        )

    async def _decide(self, ctx: AgentContext) -> AgentResult:
        """Ask the LLM for the next file action given current context."""
        messages = ctx.to_llm_messages(self.system_prompt())
        messages.append(
            LLMMessage(
                role="user",
                content=(
                    f"Goal: {ctx.goal}\n"
                    f"Step: {ctx.scratchpad.get('step', ctx.goal)}\n"
                    "Decide the next file action. If the goal is already met, "
                    "respond with action 'done'."
                ),
            )
        )
        response = await self.llm.chat(messages, temperature=0.1)
        decision = _parse_action_json(
            response.content, valid_actions=_VALID_ACTIONS, fallback="done"
        )

        action = str(decision.get("action", "done")).lower().strip()

        # 'done' or an unknown verb -> finish with a summary.
        if action == "done" or action not in _ACTION_TO_TOOL:
            return AgentResult(
                message=f"File goal complete: {response.content[:500]}",
                done=True,
            )

        tool_name, risk = _ACTION_TO_TOOL[action]
        arguments = _build_arguments(action, decision)
        return AgentResult(
            message=f"Performing {action} on {arguments.get('path') or arguments}",
            tool_call=ToolCallRequest(
                tool_name=tool_name,
                arguments=arguments,
                risk=risk,
                rationale=f"User-requested {action} operation.",
            ),
        )


def _build_arguments(action: str, decision: dict[str, Any]) -> dict[str, Any]:
    """Translate the LLM decision into the tool's argument dict per action."""
    if action == "list":
        return {"path": str(decision.get("path", ""))}
    if action == "read":
        return {"path": str(decision.get("path", ""))}
    if action == "write":
        return {
            "path": str(decision.get("path", "")),
            "content": str(decision.get("content", "")),
        }
    if action in {"copy", "move"}:
        return {
            "source": str(decision.get("source", "")),
            "destination": str(decision.get("destination", "")),
        }
    if action == "delete":
        return {"path": str(decision.get("path", ""))}
    return {}
