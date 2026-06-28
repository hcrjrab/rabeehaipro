"""Memory Agent - manages all memory systems.

This agent handles:
1. Storing and retrieving conversation history.
2. Semantic search across vector memory (ChromaDB).
3. Structured knowledge graph queries.
4. Long-term preference and project memory.
5. Memory consolidation and summarisation.

Unlike other agents, the Memory Agent is stateless — it directly queries
the MemoryService and returns structured results.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config.schemas import AgentRole
from ..memory.base import KnowledgeTriple, MemoryQuery, MemoryService
from .base import AgentContext, AgentResult, BaseAgent

_log = logging.getLogger(__name__)


class MemoryAgent(BaseAgent):
    """Agent responsible for all memory operations."""

    role: AgentRole = AgentRole.MEMORY
    description: str = "Manage conversation history, semantic search, and knowledge graph."

    def __init__(self, memory_service: MemoryService, llm: Any = None) -> None:
        super().__init__(llm=llm)
        self._memory = memory_service

    def system_prompt(self) -> str:
        return (
            "You are the Memory Agent. You manage conversation history, "
            "semantic search, and knowledge graph operations. "
            "Respond concisely with the requested memory data."
        )

    async def _run(self, ctx: AgentContext) -> AgentResult:
        """Execute a memory operation based on the goal description.

        Supported operations (detected via keywords in *goal*):
        - ``remember <content>`` — store in vector memory
        - ``search <query>`` — semantic search
        - ``history <session_id>`` — recent conversation history
        - ``learn <subj> | <pred> | <obj>`` — knowledge graph triple
        - ``ask <subject>`` — query knowledge graph
        - ``clear <session_id>`` — clear session history
        """
        goal = ctx.goal
        goal_lower = goal.lower()

        if goal_lower.startswith("remember"):
            content = goal[9:].strip()
            if not content:
                return AgentResult(
                    message="Nothing to remember.",
                    done=True,
                )
            await self._memory.remember(
                content,
                scope="long_term",
                kind="insight",
                metadata={"session_id": ctx.session_id, "task_id": str(ctx.task_id)},
            )
            return AgentResult(
                message=f"Remembered: {content[:100]}...",
                done=True,
            )

        if goal_lower.startswith("search"):
            query_text = goal[7:].strip()
            if not query_text:
                return AgentResult(message="Search query is empty.", done=True)
            results = await self._memory.search(query_text, top_k=5)
            if not results:
                return AgentResult(message=f"No results found for: {query_text}", done=True)
            summary_lines = [
                f"{i}. [score={r.score:.2f}] {r.content[:200].replace(chr(10), ' ')}"
                for i, r in enumerate(results, 1)
            ]
            return AgentResult(
                message="Search results:\n" + "\n".join(summary_lines),
                done=True,
            )

        if goal_lower.startswith("history"):
            parts = goal.split(None, 1)
            session_id = parts[1].strip() if len(parts) > 1 else ctx.session_id
            records = await self._memory.get_history(str(session_id), limit=20)
            if not records:
                return AgentResult(message=f"No history for session {session_id}.", done=True)
            lines = [
                f"[{r.created_at.isoformat() if hasattr(r.created_at, 'isoformat') else r.created_at}] {r.content[:150]}"
                for r in records
            ]
            return AgentResult(
                message=f"History for {session_id} ({len(records)} messages):\n" + "\n".join(lines),
                done=True,
            )

        if goal_lower.startswith("learn"):
            rest = goal[6:].strip()
            parts = rest.split("|")
            if len(parts) < 3:
                return AgentResult(
                    message="Usage: learn subject | predicate | object",
                    done=True,
                )
            triple = KnowledgeTriple(
                subject=parts[0].strip(),
                predicate=parts[1].strip(),
                obj=parts[2].strip(),
                source="memory_agent",
            )
            await self._memory.learn(triple)
            return AgentResult(
                message=f"Learned: ({triple.subject}) --[{triple.predicate}]--> ({triple.obj})",
                done=True,
            )

        if goal_lower.startswith("ask"):
            subject = goal[4:].strip()
            if not subject:
                return AgentResult(message="No subject specified.", done=True)
            triples = await self._memory.ask(subject)
            if not triples:
                return AgentResult(message=f"No facts known about: {subject}", done=True)
            lines = [
                f"({t.subject}) --[{t.predicate}]--> ({t.obj}) [conf: {t.confidence:.2f}]"
                for t in triples
            ]
            return AgentResult(
                message=f"Facts about {subject}:\n" + "\n".join(lines),
                done=True,
            )

        if goal_lower.startswith("clear"):
            parts = goal.split(None, 1)
            session_id = parts[1].strip() if len(parts) > 1 else ctx.session_id
            await self._memory.clear_session(str(session_id))
            return AgentResult(message=f"Cleared memory for session {session_id}.", done=True)

        query = MemoryQuery(
            text=goal,
            session_id=str(ctx.session_id),
            limit=10,
        )
        records = await self._memory.recall(query)
        if not records:
            return AgentResult(message="No relevant memories found.", done=True)
        lines = [f"[{r.scope}/{r.kind} ({r.score:.2f})] {r.content[:200]}" for r in records]
        return AgentResult(
            message="Relevant memories:\n" + "\n".join(lines),
            done=True,
        )
