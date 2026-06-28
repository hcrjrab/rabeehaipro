"""Automation agent.

Controls the user's desktop: lists windows, moves/clicks the mouse, types on
the keyboard, and reads the clipboard. Because these actions have real side
effects on the user's machine, the loop is conservative:

1. ``observe`` -> enumerate visible windows (read-only, NONE risk) so the
   agent knows what application it is targeting.
2. ``decide``  -> ask the LLM what desktop action to take next.
3. ``act``     -> execute the chosen tool.

Mouse move/click and clipboard are ``SAFE``; typing is ``DESTRUCTIVE`` (can
trigger shortcuts like delete/close) and will be intercepted by the approval
gate. The agent never runs more than ``max_steps`` actions before reporting
completion, and every decision is one tool call per step so the gate always
has a chance to pause.
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
    "click": ("mouse.click", RiskLevel.SAFE),
    "move": ("mouse.move", RiskLevel.SAFE),
    "type": ("keyboard.type", RiskLevel.DESTRUCTIVE),
    "clipboard_read": ("clipboard", RiskLevel.SAFE),
    "clipboard_write": ("clipboard", RiskLevel.SAFE),
    "done": ("", RiskLevel.NONE),
}

_VALID_ACTIONS = set(_ACTION_TO_TOOL)
_MAX_STEPS = 6


class AutomationAgent(BaseAgent):
    """Desktop-control agent (observe -> decide -> act)."""

    role = AgentRole.AUTOMATION

    def __init__(self, *, max_steps: int = _MAX_STEPS) -> None:
        super().__init__()
        self.max_steps = max_steps

    def system_prompt(self) -> str:
        return (
            "You are the Automation agent. You control the user's desktop: click, "
            "move the mouse, type, and use the clipboard. ALWAYS observe the "
            "window list before acting so you target the right application. "
            "Prefer precise coordinates. Respond with ONLY a JSON object matching "
            "exactly this schema, no markdown fences, no commentary:\n"
            "{\n"
            '  "action": "<click | move | type | clipboard_read | clipboard_write | done>",\n'
            '  "x": 0, "y": 0,           // click/move\n'
            '  "button": "left",          // click (left|right|middle)\n'
            '  "text": "...",             // type (literal text)\n'
            '  "keys": "ctrl+c",          // type (key combo)\n'
            '  "value": "..."             // clipboard_write\n'
            "}"
        )

    async def _run(self, ctx: AgentContext) -> AgentResult:
        """Drive the observe -> decide -> act state machine."""
        phase = ctx.scratchpad.get("automation_phase", "observe")
        step_no = int(ctx.scratchpad.get("automation_step", 0))

        # Step 1: observe the desktop (always read-only first).
        if phase == "observe":
            return self._observe(ctx, step_no)

        # Over-budget guard.
        if step_no >= self.max_steps:
            return AgentResult(
                message=f"Automation complete (max {self.max_steps} steps reached).",
                done=True,
            )

        ctx.scratchpad["automation_step"] = step_no + 1
        return await self._decide(ctx)

    # ------------------------------------------------------------------
    # Phases
    # ------------------------------------------------------------------
    def _observe(self, ctx: AgentContext, step_no: int) -> AgentResult:
        """Propose a read-only window listing to orient the agent."""
        ctx.scratchpad["automation_phase"] = "decide"
        ctx.scratchpad["automation_step"] = step_no + 1
        return AgentResult(
            message="Listing visible windows before automating.",
            tool_call=ToolCallRequest(
                tool_name="window.list",
                arguments={},
                risk=RiskLevel.NONE,
                rationale="Observe the desktop state before any input action.",
            ),
        )

    async def _decide(self, ctx: AgentContext) -> AgentResult:
        """Ask the LLM for the next desktop action."""
        messages = ctx.to_llm_messages(self.system_prompt())
        messages.append(
            LLMMessage(
                role="user",
                content=(
                    f"Goal: {ctx.goal}\n"
                    f"Step: {ctx.scratchpad.get('step', ctx.goal)}\n"
                    "Decide the next desktop action. If the goal is met, "
                    "respond with action 'done'."
                ),
            )
        )
        response = await self.llm.chat(messages, temperature=0.1)
        decision = _parse_action_json(
            response.content, valid_actions=_VALID_ACTIONS, fallback="done"
        )

        action = str(decision.get("action", "done")).lower().strip()
        if action == "done" or action not in _ACTION_TO_TOOL:
            return AgentResult(
                message=f"Automation goal complete: {response.content[:500]}",
                done=True,
            )

        tool_name, risk = _ACTION_TO_TOOL[action]
        arguments = _build_arguments(action, decision)
        return AgentResult(
            message=f"Performing desktop {action}",
            tool_call=ToolCallRequest(
                tool_name=tool_name,
                arguments=arguments,
                risk=risk,
                rationale=f"User-requested desktop {action} action.",
            ),
        )


def _build_arguments(action: str, decision: dict[str, Any]) -> dict[str, Any]:
    """Translate the LLM decision into the tool's argument dict per action."""
    if action in {"click", "move"}:
        args: dict[str, Any] = {
            "x": int(decision.get("x", 0)),
            "y": int(decision.get("y", 0)),
        }
        if action == "click":
            args["button"] = str(decision.get("button", "left"))
        else:
            args["duration"] = float(decision.get("duration", 0.25))
        return args
    if action == "type":
        args = {}
        if decision.get("text"):
            args["text"] = str(decision["text"])
        elif decision.get("keys"):
            args["keys"] = str(decision["keys"])
        return args
    if action == "clipboard_read":
        return {"action": "read"}
    if action == "clipboard_write":
        return {"action": "write", "text": str(decision.get("value", ""))}
    return {}
