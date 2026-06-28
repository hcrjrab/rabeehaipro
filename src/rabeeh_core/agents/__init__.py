"""Agent bounded context.

Defines the common ``BaseAgent`` contract every specialised agent (planner,
coding, research, vision, browser, ...) implements. Agents are the *thinking*
units; tools are the *acting* units. Agents never touch the OS directly —
they propose :class:`ToolCallRequest` objects that the orchestrator executes
through the approval gate.

This separation is the backbone of the safety model: an agent cannot do
anything the orchestrator doesn't permit.
"""

from __future__ import annotations

import logging

from ..config.schemas import AgentRole
from ..llm.base import LLMClient
from .automation import AutomationAgent
from .base import AgentContext, AgentResult, BaseAgent
from .browser import BrowserAgent
from .business import BusinessAgent
from .coding import CodingAgent
from .file import FileAgent
from .memory_agent import MemoryAgent
from .office import OfficeAgent
from .planner import PlannerAgent
from .research import ResearchAgent
from .reviewer import ReviewerAgent
from .vision import VisionAgent

_log = logging.getLogger(__name__)

__all__ = [
    "AgentContext",
    "AgentResult",
    "AutomationAgent",
    "BaseAgent",
    "BrowserAgent",
    "CodingAgent",
    "FileAgent",
    "MemoryAgent",
    "OfficeAgent",
    "PlannerAgent",
    "ResearchAgent",
    "ReviewerAgent",
    "VisionAgent",
    "create_default_agents",
]


def create_default_agents(llm: LLMClient | None = None) -> dict[AgentRole, BaseAgent]:
    """Instantiate the standard agent pool keyed by :class:`AgentRole`.

    Every role in :class:`AgentRole` that maps to a concrete agent gets wired
    here, so the orchestrator can look up any role via ``agents[role]``. The
    factory is the single source of truth for "what agents ship by default" —
    adding a new agent is a one-line change here.

    Parameters
    ----------
    llm:
        Optional shared :class:`LLMClient`. When omitted each agent falls back
        to the process-wide client (``get_client``), which is the mock in tests
        and the configured router in production.

    Returns
    -------
    dict[AgentRole, BaseAgent]
        A fresh mapping; callers may mutate it (e.g. drop a role, swap an
        agent) without affecting future calls.
    """
    pool: dict[AgentRole, BaseAgent] = {
        AgentRole.PLANNER: PlannerAgent(llm=llm) if _accepts_llm(PlannerAgent) else PlannerAgent(),
        AgentRole.REVIEWER: ReviewerAgent(llm=llm)
        if _accepts_llm(ReviewerAgent)
        else ReviewerAgent(),
        AgentRole.RESEARCH: ResearchAgent(llm=llm)
        if _accepts_llm(ResearchAgent)
        else ResearchAgent(),
        AgentRole.CODING: CodingAgent(llm=llm) if _accepts_llm(CodingAgent) else CodingAgent(),
        AgentRole.OFFICE: OfficeAgent(llm=llm) if _accepts_llm(OfficeAgent) else OfficeAgent(),
        AgentRole.VISION: VisionAgent(),
        AgentRole.BROWSER: BrowserAgent(),
        AgentRole.AUTOMATION: AutomationAgent(),
        AgentRole.FILE: FileAgent(),
        AgentRole.MEMORY: _build_memory_agent(llm=llm),
        AgentRole.BUSINESS: _build_business_agent(),
    }
    return pool


def _build_memory_agent(llm: LLMClient | None = None) -> MemoryAgent:
    """Construct the Memory Agent with the default memory service."""
    from ..config.settings import get_settings
    from ..memory.base import MemoryService
    from ..memory.chroma_store import CHROMA_ENABLED, ChromaMemoryStore
    from ..memory.in_memory import InMemoryStore
    from ..memory.knowledge_graph import SQLiteKnowledgeGraph

    settings = get_settings()
    conversation_store = InMemoryStore()

    vector_store = None
    if CHROMA_ENABLED:
        try:
            vector_store = ChromaMemoryStore(persist_directory=settings.chroma_path)
        except Exception as exc:
            _log.warning("ChromaDB init failed: %s", exc)

    kg = None
    try:
        kg = SQLiteKnowledgeGraph(db_path=settings.data_dir / "knowledge_graph.db")
    except Exception as exc:
        _log.warning("Knowledge graph init failed: %s", exc)

    memory_service = MemoryService(
        conversation_store=conversation_store,
        vector_store=vector_store,
        knowledge_graph=kg,
    )
    return MemoryAgent(memory_service=memory_service, llm=llm)


def _build_business_agent() -> BusinessAgent:
    """Construct a Business Agent instance."""
    return BusinessAgent()


def _accepts_llm(agent_cls: type[BaseAgent]) -> bool:
    """True if ``agent_cls.__init__`` accepts an ``llm`` keyword.

    The base ``BaseAgent.__init__`` takes ``llm``, but some concrete agents
    override ``__init__`` with only keyword-only config (e.g. ``max_steps``)
    and route the LLM through ``super().__init__()``. We reflect on the
    signature so the factory never passes an unexpected argument.
    """
    import inspect

    params = inspect.signature(agent_cls.__init__).parameters
    return "llm" in params
