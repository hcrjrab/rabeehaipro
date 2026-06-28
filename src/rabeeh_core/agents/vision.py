"""Vision agent.

Perceives the desktop via screenshots and OCR. The loop is:

1. ``capture`` -> take a screenshot + OCR it in one ``screen.read`` call.
2. ``interpret`` -> feed the extracted text to the LLM and either answer the
   user's question about the screen or decide what to look at next.
3. ``done`` -> final description / answer.

Step 1 is a single read-only (NONE risk) tool call so the agent can see the
screen before deciding anything. The agent never moves the mouse or clicks —
that is the :mod:`~rabeeh_core.agents.automation` agent's job — it only
*reads* the visual state.
"""

from __future__ import annotations

import logging

from ..config.schemas import AgentRole, RiskLevel, ToolCallRequest
from ..llm.base import LLMMessage
from .base import AgentContext, AgentResult, BaseAgent

_log = logging.getLogger(__name__)

_MAX_LOOKS = 3  # screenshot rounds before forcing an answer


class VisionAgent(BaseAgent):
    """Screen-reading agent: capture -> OCR -> interpret."""

    role = AgentRole.VISION

    def __init__(self, *, max_looks: int = _MAX_LOOKS) -> None:
        super().__init__()
        self.max_looks = max_looks

    def system_prompt(self) -> str:
        return (
            "You are the Vision agent. You understand what is on the user's "
            "screen by reading OCR text extracted from screenshots. Describe "
            "the visible UI, answer questions about it, or identify elements "
            "another agent should interact with. Be concise and factual; never "
            "invent text that is not in the OCR output."
        )

    async def _run(self, ctx: AgentContext) -> AgentResult:
        """Drive the capture -> interpret state machine."""
        phase = ctx.scratchpad.get("vision_phase", "capture")
        looks = int(ctx.scratchpad.get("vision_looks", 0))

        # Step 1: always capture the screen first (read-only).
        if phase == "capture":
            ctx.scratchpad["vision_phase"] = "interpret"
            ctx.scratchpad["vision_looks"] = looks + 1
            return AgentResult(
                message="Capturing the screen to read its contents.",
                tool_call=ToolCallRequest(
                    tool_name="screen.read",
                    arguments={},
                    risk=RiskLevel.NONE,
                    rationale="Read the current screen state before interpreting it.",
                ),
            )

        # Step 2+: interpret the OCR text (or re-capture if needed).
        return await self._interpret(ctx, looks)

    async def _interpret(self, ctx: AgentContext, looks: int) -> AgentResult:
        """Ask the LLM to interpret the latest OCR output."""
        # The orchestrator feeds tool results back via the conversation; pull
        # the most recent screen.read text from the scratchpad if the runner
        # staged it, else rely on history.
        screen_text = str(ctx.scratchpad.get("vision_text", ""))
        forced_done = looks >= self.max_looks

        messages = ctx.to_llm_messages(self.system_prompt())
        prompt = f"Goal: {ctx.goal}\n" f"Step: {ctx.scratchpad.get('step', ctx.goal)}\n"
        if screen_text:
            prompt += f"\nLatest screen OCR text:\n{screen_text[:4000]}\n"
        prompt += (
            "\nDecide the next action. Reply with ONLY one of:\n"
            "- LOOK: <reason to re-capture the screen>\n"
            "- DONE: <your final answer about what is on screen>\n"
        )
        if forced_done:
            prompt += "You must answer DONE (max looks reached)."
        messages.append(LLMMessage(role="user", content=prompt))

        response = await self.llm.chat(messages, temperature=0.1)
        decision = response.content.strip()

        if decision.upper().startswith("LOOK:") and not forced_done:
            ctx.scratchpad["vision_phase"] = "capture"
            return AgentResult(
                message=f"Re-capturing screen: {decision.split(':', 1)[1].strip()}",
                tool_call=ToolCallRequest(
                    tool_name="screen.read",
                    arguments={},
                    risk=RiskLevel.NONE,
                ),
            )

        # DONE (or forced completion / unparseable).
        answer = decision.split(":", 1)[1].strip() if ":" in decision else decision
        return AgentResult(
            message=f"Screen analysis: {answer[:1000]}",
            done=True,
        )
