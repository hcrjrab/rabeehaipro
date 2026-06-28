"""Browser agent.

Drives a headless browser to research, navigate, extract and fill forms on
the web. It runs an autonomous loop bounded by a step cap:

1. First step is always a ``web.search`` (read-only) to find relevant pages.
2. Subsequent steps defer to the LLM, which returns a structured decision:
   ``SEARCH`` | ``FETCH`` | ``EXTRACT`` | ``CLICK`` | ``FILL`` | ``DONE``.
3. ``CLICK`` is the only DESTRUCTIVE action (can trigger navigation/submit);
   everything else is NONE or SAFE, so most steps never hit the approval gate.

The agent never handles credentials or authentication — that is RBAC/secret
work landing in Phase 6. It operates on public pages only.
"""

from __future__ import annotations

import logging

from ..config.schemas import AgentRole, RiskLevel, ToolCallRequest
from ..llm.base import LLMMessage
from .base import AgentContext, AgentResult, BaseAgent

_log = logging.getLogger(__name__)

_MAX_STEPS = 6  # search/fetch/click rounds before forcing completion


class BrowserAgent(BaseAgent):
    """Web-grounded browsing agent (search -> read -> act -> done)."""

    role = AgentRole.BROWSER

    def __init__(self, *, max_steps: int = _MAX_STEPS) -> None:
        super().__init__()
        self.max_steps = max_steps

    def system_prompt(self) -> str:
        return (
            "You are the Browser agent. You navigate the web to accomplish the "
            "user's goal: search, read pages, extract data, click links, and fill "
            "forms. Be efficient: prefer reading over clicking, and never click "
            "or submit unless clearly required. "
            f"Stop after at most {self.max_steps} steps and summarise the outcome."
        )

    async def _run(self, ctx: AgentContext) -> AgentResult:
        """Decide the next browsing action via the LLM (one tool call per step)."""
        round_no = int(ctx.scratchpad.get("browser_round", 0))
        ctx.scratchpad["browser_round"] = round_no + 1

        # Step 1: always start with a search.
        if round_no == 0:
            return AgentResult(
                message=f"Starting browser search for: {ctx.goal}",
                tool_call=ToolCallRequest(
                    tool_name="web.search",
                    arguments={"query": ctx.goal, "limit": 5},
                    risk=RiskLevel.NONE,
                    rationale="Initial search to find relevant pages.",
                ),
            )

        # Step cap reached: force a summary.
        if round_no >= self.max_steps:
            return AgentResult(
                message=f"Browser task concluded (max {self.max_steps} steps reached).",
                done=True,
            )

        # Ask the LLM for the next action.
        messages = ctx.to_llm_messages(self.system_prompt())
        messages.append(
            LLMMessage(
                role="user",
                content=(
                    f"Goal: {ctx.goal}\n"
                    f"You have completed {round_no} step(s). "
                    "Decide the next action. Reply with ONLY one of:\n"
                    "- SEARCH: <new query>\n"
                    "- FETCH: <url>\n"
                    "- EXTRACT: <url> | <css selector>\n"
                    "- CLICK: <url> | <css selector>\n"
                    "- FILL: <url> | <css selector> | <value>\n"
                    "- DONE: <final summary>\n"
                    f"You must answer DONE if the goal is met or after {self.max_steps} steps."
                ),
            )
        )
        response = await self.llm.chat(messages, temperature=0.1)
        return _parse_browser_decision(response.content)


def _parse_browser_decision(raw: str) -> AgentResult:
    """Convert the LLM's structured decision into an :class:`AgentResult`."""
    decision = raw.strip()
    upper = decision.upper()

    if upper.startswith("SEARCH:"):
        query = decision.split(":", 1)[1].strip()
        return AgentResult(
            message=f"Searching for: {query}",
            tool_call=ToolCallRequest(
                tool_name="web.search",
                arguments={"query": query, "limit": 5},
                risk=RiskLevel.NONE,
            ),
        )
    if upper.startswith("FETCH:"):
        url = decision.split(":", 1)[1].strip()
        return AgentResult(
            message=f"Fetching: {url}",
            tool_call=ToolCallRequest(
                tool_name="web.fetch",
                arguments={"url": url},
                risk=RiskLevel.NONE,
            ),
        )
    if upper.startswith("EXTRACT:"):
        url, selector = _split_pipe(decision.split(":", 1)[1], default_sel="a")
        return AgentResult(
            message=f"Extracting '{selector}' from {url}",
            tool_call=ToolCallRequest(
                tool_name="web.extract",
                arguments={"url": url, "selector": selector, "limit": 20},
                risk=RiskLevel.NONE,
            ),
        )
    if upper.startswith("CLICK:"):
        url, selector = _split_pipe(decision.split(":", 1)[1], default_sel="body")
        return AgentResult(
            message=f"Clicking '{selector}' on {url}",
            tool_call=ToolCallRequest(
                tool_name="web.click",
                arguments={"url": url, "selector": selector},
                risk=RiskLevel.DESTRUCTIVE,
                rationale="Clicking may trigger navigation or form submission.",
            ),
        )
    if upper.startswith("FILL:"):
        url, selector, value = _split_pipe3(decision.split(":", 1)[1])
        return AgentResult(
            message=f"Filling '{selector}' on {url}",
            tool_call=ToolCallRequest(
                tool_name="web.fill_form",
                arguments={"url": url, "selector": selector, "value": value},
                risk=RiskLevel.SAFE,
            ),
        )
    if upper.startswith("DONE:"):
        summary = decision.split(":", 1)[1].strip() if ":" in decision else decision
        return AgentResult(message=summary, done=True)

    # Unparseable: treat the response as a rough summary and finish.
    return AgentResult(message=f"Browser summary: {decision[:1000]}", done=True)


def _split_pipe(rest: str, *, default_sel: str) -> tuple[str, str]:
    """Split 'url | selector' into a (url, selector) pair."""
    if "|" in rest:
        url, selector = rest.split("|", 1)
        return url.strip(), selector.strip() or default_sel
    return rest.strip(), default_sel


def _split_pipe3(rest: str) -> tuple[str, str, str]:
    """Split 'url | selector | value' into a (url, selector, value) triple."""
    parts = [p.strip() for p in rest.split("|")]
    url = parts[0] if parts else ""
    selector = parts[1] if len(parts) > 1 else "input"
    value = parts[2] if len(parts) > 2 else ""
    return url, selector, value
