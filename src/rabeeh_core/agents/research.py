"""Research agent.

Gathers information on a topic using web tools (search + fetch) and memory
recall, then synthesises a concise briefing. It runs autonomously for a
bounded number of iterations: search, read top results, summarise, and stop
when it has enough material (or hits the iteration cap).

The agent is deliberately conservative: it only reads (NONE-risk tools), so
it never triggers the approval gate.
"""

from __future__ import annotations

import logging

from ..config.schemas import AgentRole, RiskLevel, ToolCallRequest
from ..llm.base import LLMClient, LLMMessage
from .base import AgentContext, AgentResult, BaseAgent

_log = logging.getLogger(__name__)

_MAX_RESEARCH_STEPS = 4  # search/fetch rounds before forcing a summary


class ResearchAgent(BaseAgent):
    """Web-grounded information gatherer."""

    role = AgentRole.RESEARCH

    def __init__(
        self, llm: LLMClient | None = None, *, max_steps: int = _MAX_RESEARCH_STEPS
    ) -> None:
        super().__init__(llm=llm)
        self.max_steps = max_steps

    def system_prompt(self) -> str:
        return (
            "You are the Research agent. Given a question or topic, use the "
            "``web.search`` tool to find relevant sources, then ``web.fetch`` to "
            "read the most promising results. Synthesise a concise, factual "
            "briefing with citations (URLs). Never fabricate facts; if a source "
            "doesn't answer the question, search again with different terms. "
            f"Stop after at most {self.max_steps} rounds and summarise what you found."
        )

    async def _run(self, ctx: AgentContext) -> AgentResult:
        """Decide the next research action via the LLM.

        Returns a tool call (web.search / web.fetch) or a final summary. The
        orchestrator executes the tool and feeds the result back; this method
        is called once per orchestrator step.
        """
        # Count how many tool results we've already accumulated for this task.
        prior_results = ctx.scratchpad.get("research_round", 0)

        # First step: always start with a search.
        if prior_results == 0:
            ctx.scratchpad["research_round"] = 1
            return AgentResult(
                message=f"Starting research on: {ctx.goal}",
                tool_call=ToolCallRequest(
                    tool_name="web.search",
                    arguments={"query": ctx.goal, "limit": 5},
                    risk=RiskLevel.NONE,
                    rationale="Initial search to find relevant sources.",
                ),
            )

        # Subsequent steps: ask the LLM whether to search more, fetch a URL,
        # or summarise. We feed it the conversation so far.
        ctx.scratchpad["research_round"] = prior_results + 1
        messages = ctx.to_llm_messages(self.system_prompt())
        messages.append(
            LLMMessage(
                role="user",
                content=(
                    f"Research goal: {ctx.goal}\n"
                    f"You have completed {prior_results} step(s). "
                    f"Decide the next action. Reply with ONLY one of:\n"
                    "- SEARCH: <new query>\n"
                    "- FETCH: <url>\n"
                    "- DONE: <your final briefing>\n"
                    f"You must answer DONE if you have done {self.max_steps} steps."
                ),
            )
        )
        response = await self.llm.chat(messages, temperature=0.1)
        decision = response.content.strip()

        # Parse the LLM's structured decision.
        if decision.upper().startswith("SEARCH:"):
            query = decision.split(":", 1)[1].strip()
            return AgentResult(
                message=f"Searching for: {query}",
                tool_call=ToolCallRequest(
                    tool_name="web.search",
                    arguments={"query": query, "limit": 5},
                    risk=RiskLevel.NONE,
                ),
            )
        if decision.upper().startswith("FETCH:"):
            url = decision.split(":", 1)[1].strip()
            return AgentResult(
                message=f"Fetching: {url}",
                tool_call=ToolCallRequest(
                    tool_name="web.fetch",
                    arguments={"url": url},
                    risk=RiskLevel.NONE,
                ),
            )
        if decision.upper().startswith("DONE:"):
            briefing = decision.split(":", 1)[1].strip() if ":" in decision else decision
            return AgentResult(message=briefing, done=True)

        # Force completion if we've hit the step cap or the response was unparseable.
        if prior_results >= self.max_steps:
            return AgentResult(
                message=f"Research summary (max steps reached): {decision[:1000]}",
                done=True,
            )
        # Unparseable but under cap: treat the response itself as a rough summary
        # and let the orchestrator/reviewer decide.
        return AgentResult(message=decision[:1000])
