"""LangGraph-backed orchestrator (Phase 2).

Promotes the Phase 1 linear runner into a real ``StateGraph``:

    START -> plan -> execute_step -> review -> {pass: next|finish,
                                                fail: record_error|finish,
                                                replan: plan}

Why a graph?
- Conditional edges encode the review-driven control flow declaratively.
- LangGraph's checkpointing (Phase 6) will let us resume long-running or
  approval-paused tasks from disk — impossible with a bare loop.
- The same node functions are plain callables, so they remain unit-testable
  in isolation without instantiating a graph.

Design note: langgraph is an *optional* dependency. If it is absent, the app
falls back to :class:`~rabeeh_core.orchestration.runner.SimpleOrchestrator`.
Importing this module eagerly would break ``pip install`` without the
``langgraph`` extra, so :func:`build_graph` imports langgraph lazily.
"""

from __future__ import annotations

import logging
from typing import Any, Literal
from uuid import UUID

from ..agents.planner import PlannerAgent
from ..agents.reviewer import ReviewerAgent
from ..config.schemas import TaskStatus
from ..config.settings import get_settings
from ..llm.base import LLMClient
from ..llm.registry import get_client
from ..memory.base import MemoryStore
from ..memory.in_memory import InMemoryStore
from ..security.approval import ApprovalGate
from ..tools.registry import ToolRegistry, get_registry
from .runner import Orchestrator  # reuse node logic + plan parsing
from .state import OrchestratorState

_log = logging.getLogger(__name__)

# Route labels returned by the review router.
RouteAfterReview = Literal["next_step", "replan", "finish", "await_approval"]


class GraphOrchestrator:
    """Drives a task via a LangGraph ``StateGraph`` with review-driven edges.

    Reuses :class:`Orchestrator` for the actual node bodies (planning,
    tool-call handling, agent dispatch) so behaviour stays identical to the
    linear runner; only the *control flow* is expressed as a graph.
    """

    def __init__(
        self,
        *,
        llm: LLMClient | None = None,
        tools: ToolRegistry | None = None,
        memory: MemoryStore | None = None,
        gate: ApprovalGate | None = None,
        planner: PlannerAgent | None = None,
        reviewer: ReviewerAgent | None = None,
    ) -> None:
        self.llm = llm or get_client()
        self.tools = tools or get_registry()
        self.memory = memory or InMemoryStore()
        self.gate = gate or ApprovalGate()
        self.planner = planner or PlannerAgent(self.llm)
        self.reviewer = reviewer or ReviewerAgent(self.llm)

        # The inner runner owns the shared node logic (plan, tool handling).
        self._runner = Orchestrator(
            llm=self.llm, tools=self.tools, memory=self.memory, gate=self.gate
        )
        self._runner.register_agent(self.planner)
        self._runner.register_agent(self.reviewer)

        self._graph = self._build_graph()

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------
    def _build_graph(self) -> Any:
        """Construct and compile the LangGraph state graph.

        langgraph is imported lazily here so the module imports cleanly even
        when the extra is not installed.
        """
        from langgraph.graph import END, START, StateGraph

        builder: StateGraph = StateGraph(dict)  # type: ignore[type-arg]

        builder.add_node("plan", self._node_plan)  # type: ignore[type-var]
        builder.add_node("execute", self._node_execute)  # type: ignore[type-var]
        builder.add_node("review", self._node_review)  # type: ignore[type-var]

        builder.add_edge(START, "plan")
        builder.add_conditional_edges(
            "plan",
            self._route_after_plan,
            {"execute": "execute", "finish": END},
        )
        builder.add_edge("execute", "review")
        builder.add_conditional_edges(
            "review",
            self._route_after_review,
            {
                "next_step": "execute",
                "replan": "plan",
                "finish": END,
                "await_approval": END,
            },
        )
        return builder.compile()

    # ------------------------------------------------------------------
    # Nodes (thin async adapters over Orchestrator logic)
    # ------------------------------------------------------------------
    # Nodes are async so we can ``await`` the orchestrator's async helpers
    # directly. langgraph runs async nodes on its own event loop — never mix
    # ``run_until_complete`` inside a node (it would deadlock on the running
    # loop).
    async def _node_plan(self, state: dict[str, Any]) -> dict[str, Any]:
        """Run the planner and store the resulting plan in state."""
        orch_state = _state_from_dict(state)
        await self._runner._plan(orch_state)
        return _state_to_dict(orch_state)

    async def _node_execute(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute the current step (one iteration of the runner loop)."""
        orch_state = _state_from_dict(state)
        await self._runner._execute_one_step(orch_state)
        return _state_to_dict(orch_state)

    async def _node_review(self, state: dict[str, Any]) -> dict[str, Any]:
        """Run the reviewer over the just-executed step."""
        orch_state = _state_from_dict(state)
        verdict = await self._review_step(orch_state)
        orch_state.scratchpad["last_verdict"] = verdict
        return _state_to_dict(orch_state)

    async def _review_step(self, orch_state: OrchestratorState) -> str:
        """Invoke the reviewer and return its verdict token."""
        if orch_state.status in {TaskStatus.AWAITING_APPROVAL, TaskStatus.FAILED}:
            return "finish"
        ctx = await self._runner._make_ctx(orch_state)
        ctx.scratchpad["tool_results"] = [r.model_dump() for r in orch_state.tool_results[-3:]]
        result = await self.reviewer.run(ctx)
        verdict = str(result.extra.get("verdict", "fail"))
        orch_state.add_event("review", {"verdict": verdict, "reason": result.extra.get("reason")})
        return verdict

    # ------------------------------------------------------------------
    # Routers (conditional edges)
    # ------------------------------------------------------------------
    def _route_after_plan(self, state: dict[str, Any]) -> str:
        orch_state = _state_from_dict(state)
        if orch_state.status == TaskStatus.FAILED:
            return "finish"
        if orch_state.plan is None:
            return "finish"
        return "execute"

    def _route_after_review(self, state: dict[str, Any]) -> RouteAfterReview:
        orch_state = _state_from_dict(state)
        if orch_state.status == TaskStatus.AWAITING_APPROVAL:
            return "await_approval"
        if orch_state.status == TaskStatus.FAILED:
            return "finish"
        if orch_state.is_over_budget():
            orch_state.add_event("budget_exceeded", {"iterations": orch_state.iterations})
            return "finish"

        verdict = orch_state.scratchpad.get("last_verdict", "fail")
        steps_done = orch_state.plan and all(s.done for s in orch_state.plan.steps)
        if verdict == "pass" and steps_done:
            orch_state.status = TaskStatus.COMPLETED
            orch_state.add_event("task_completed", {})
            return "finish"
        if verdict == "replan":
            return "replan"
        if verdict == "fail":
            orch_state.add_event("step_failed_review", {})
            # One retry of the same step is allowed; then finish.
            if orch_state.scratchpad.get("consecutive_failures", 0) >= 1:
                orch_state.status = TaskStatus.FAILED
                orch_state.error = "Reviewer failed the step twice."
                return "finish"
            orch_state.scratchpad["consecutive_failures"] = (
                orch_state.scratchpad.get("consecutive_failures", 0) + 1
            )
            return "next_step"
        # pass but more steps remain
        orch_state.scratchpad["consecutive_failures"] = 0
        return "next_step"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def run(self, goal: str, session_id: UUID | None = None) -> OrchestratorState:
        """Execute a goal through the compiled graph and return final state."""
        from uuid import UUID, uuid4

        if session_id is not None and not isinstance(session_id, UUID):
            session_id = UUID(str(session_id))

        settings = get_settings()
        orch_state = OrchestratorState(
            goal=goal,
            session_id=session_id or uuid4(),
            max_iterations=settings.max_orchestrator_iterations,
        )
        orch_state.add_event("task_started", {"goal": goal})

        initial = _state_to_dict(orch_state)
        # Nodes are async, so the graph MUST be driven via the async API.
        # langgraph 1.x raises if async nodes are reached through .invoke().
        final = await self._graph.ainvoke(initial)
        result_state = _state_from_dict(final)

        if result_state.status not in {
            TaskStatus.FAILED,
            TaskStatus.AWAITING_APPROVAL,
            TaskStatus.COMPLETED,
        }:
            result_state.status = TaskStatus.COMPLETED
            result_state.add_event("task_completed", {})
        return result_state


# ---------------------------------------------------------------------------
# State (de)serialisation for the graph (dict <-> OrchestratorState)
# ---------------------------------------------------------------------------
def _state_to_dict(state: OrchestratorState) -> dict[str, Any]:
    """Serialize orchestrator state into a plain dict for LangGraph."""
    return {"orch_state": state, "snapshot": state.snapshot()}


def _state_from_dict(state: dict[str, Any]) -> OrchestratorState:
    """Deserialize the dict back into the live OrchestratorState object.

    The object is carried by reference (``orch_state`` key) so mutations in a
    node are visible to the next; the ``snapshot`` key is diagnostic only.
    """
    return state["orch_state"]  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Process-wide accessor
# ---------------------------------------------------------------------------
_graph_orchestrator: GraphOrchestrator | None = None


def get_graph_orchestrator() -> GraphOrchestrator:
    """Return the shared graph orchestrator (lazy)."""
    global _graph_orchestrator
    if _graph_orchestrator is None:
        _graph_orchestrator = GraphOrchestrator()
    return _graph_orchestrator


def reset_graph_orchestrator() -> None:
    """Reset the singleton (tests)."""
    global _graph_orchestrator
    _graph_orchestrator = None
