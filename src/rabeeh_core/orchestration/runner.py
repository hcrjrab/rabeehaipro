"""Simple in-process orchestrator (Phase 1).

A linear, fully-auditable loop:

    plan  ->  for each step:
                pick agent  ->  agent.run  ->  if tool_call:
                    gate.evaluate  ->  if ALLOW: execute + record
                                     if DEFER: park (await approval)
                record message
    ->  mark COMPLETED / FAILED

This is deliberately *not* LangGraph yet: it's a small, debuggable runner
that exercises every abstraction (agents, tools, gate, memory, events) end
to end with the mock LLM. Phase 2 promotes the same nodes into a
``langgraph.StateGraph`` without changing their signatures.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID, uuid4

from ..agents.base import AgentContext, BaseAgent
from ..config.schemas import (
    AgentMessage,
    AgentRole,
    TaskPlan,
    TaskStatus,
    ToolCallRequest,
)
from ..config.settings import get_settings
from ..llm.base import LLMClient
from ..llm.registry import get_client
from ..memory.base import MemoryRecord, MemoryStore
from ..memory.in_memory import InMemoryStore
from ..security.approval import ApprovalDecision, ApprovalGate
from ..tools.base import ToolContext
from ..tools.registry import ToolRegistry, get_registry
from .state import OrchestratorState

_log = logging.getLogger(__name__)


class Orchestrator:
    """Drives a task from goal to completion (or structured failure).

    The orchestrator owns *flow control and safety*; agents own *reasoning*.
    """

    def __init__(
        self,
        *,
        llm: LLMClient | None = None,
        tools: ToolRegistry | None = None,
        memory: MemoryStore | None = None,
        gate: ApprovalGate | None = None,
        agents: dict[AgentRole, BaseAgent] | None = None,
    ) -> None:
        self.llm = llm or get_client()
        self.tools = tools or get_registry()
        self.memory = memory or InMemoryStore()
        self.gate = gate or ApprovalGate()
        # Planner is mandatory; others are looked up per-step (may be absent).
        self._agents: dict[AgentRole, BaseAgent] = agents or {}

    # ------------------------------------------------------------------
    # Agent registration
    # ------------------------------------------------------------------
    def register_agent(self, agent: BaseAgent) -> None:
        """Add an agent to the pool keyed by its role."""
        self._agents[agent.role] = agent
        _log.debug("Registered agent role=%s", agent.role)

    def _agent_for(self, role: AgentRole) -> BaseAgent | None:
        return self._agents.get(role)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def run(self, goal: str, session_id: UUID | None = None) -> OrchestratorState:
        """Execute a goal and return the final state (auditable snapshot)."""
        settings = get_settings()
        state = OrchestratorState(
            goal=goal,
            session_id=session_id or uuid4(),
            max_iterations=settings.max_orchestrator_iterations,
        )
        state.status = TaskStatus.PLANNING
        state.add_event("task_started", {"goal": goal})

        try:
            await self._plan(state)
            await self._execute(state)
            if state.status not in {TaskStatus.FAILED, TaskStatus.AWAITING_APPROVAL}:
                state.status = TaskStatus.COMPLETED
                state.add_event("task_completed", {})
        except Exception as exc:
            state.status = TaskStatus.FAILED
            state.error = str(exc)
            state.add_event("task_failed", {"error": str(exc)})
            _log.exception("Orchestrator run failed (task=%s)", state.id)

        await _persist_memory(self.memory, state)
        return state

    # ------------------------------------------------------------------
    # Stages
    # ------------------------------------------------------------------
    async def _plan(self, state: OrchestratorState) -> None:
        """Ask the planner agent to decompose the goal into steps."""
        planner = self._agent_for(AgentRole.PLANNER)
        if planner is None:
            # No planner registered: synthesise a trivial single-step plan so
            # the loop still works (useful for tests and the mock provider).
            from ..config.schemas import TaskStep

            state.plan = TaskPlan(
                goal=state.goal,
                steps=[
                    TaskStep(
                        description=state.goal,
                        assigned_agent=AgentRole.OFFICE,
                    )
                ],
                notes="No planner agent; synthesised single-step plan.",
            )
            state.add_event("plan_synthesised", {"steps": 1})
            return

        ctx = await self._make_ctx(state)
        result = await planner.run(ctx)
        if result.message is None:
            raise RuntimeError("Planner returned no plan message.")
        state.append_message(
            AgentMessage(role="assistant", name=planner.name, content=result.message)
        )
        state.plan = _parse_plan(result.message, state.goal)
        state.add_event("plan_created", {"steps": len(state.plan.steps)})

    async def _execute(self, state: OrchestratorState) -> None:
        """Walk the plan, dispatching each step to its assigned agent."""
        assert state.plan is not None
        state.status = TaskStatus.RUNNING

        for index, _step in enumerate(state.plan.steps):
            if state.is_over_budget():
                state.add_event("budget_exceeded", {"iterations": state.iterations})
                state.error = "Iteration budget exceeded."
                state.status = TaskStatus.FAILED
                return

            stop = await self._execute_one_step(state, step_index=index)
            if stop:
                return

    async def _execute_one_step(
        self, state: OrchestratorState, *, step_index: int | None = None
    ) -> bool:
        """Execute exactly one plan step. Returns True if the loop should stop.

        Extracted from ``_execute`` so the LangGraph orchestrator can drive
        steps one at a time via its own control flow. ``step_index`` defaults
        to the first not-yet-done step when omitted.
        """
        assert state.plan is not None
        state.status = TaskStatus.RUNNING

        if step_index is None:
            step_index = next(
                (i for i, s in enumerate(state.plan.steps) if not s.done),
                len(state.plan.steps) - 1,
            )
        step = state.plan.steps[step_index]

        if state.is_over_budget():
            state.add_event("budget_exceeded", {"iterations": state.iterations})
            state.error = "Iteration budget exceeded."
            state.status = TaskStatus.FAILED
            return True

        agent = self._agent_for(step.assigned_agent)
        state.iterations += 1
        if agent is None:
            state.add_event(
                "step_skipped",
                {"step": step_index, "reason": f"no agent for role {step.assigned_agent}"},
            )
            step.done = True
            return False

        ctx = await self._make_ctx(state)
        ctx.scratchpad["step"] = step.description
        result = await agent.run(ctx)

        if result.message:
            state.append_message(
                AgentMessage(role="assistant", name=agent.name, content=result.message)
            )
        if result.tool_call is not None:
            await self._handle_tool_call(state, result.tool_call)

        if state.status == TaskStatus.AWAITING_APPROVAL:
            state.add_event(
                "paused_for_approval",
                {
                    "step": step_index,
                    "tool": result.tool_call.tool_name if result.tool_call else None,
                },
            )
            return True  # Stop the loop; caller/UI resumes after approval.

        step.done = True
        state.add_event("step_done", {"step": step_index})
        return False

    async def _handle_tool_call(self, state: OrchestratorState, call: ToolCallRequest) -> None:
        """Evaluate the approval gate and (if allowed) run the tool."""
        verdict = self.gate.evaluate(call)
        state.add_event(
            "tool_call",
            {
                "tool": call.tool_name,
                "risk": call.risk.value,
                "verdict": verdict.decision.value,
                "reason": verdict.reason,
            },
        )

        if verdict.decision is ApprovalDecision.DENY:
            state.error = f"Tool {call.tool_name} denied: {verdict.reason}"
            state.status = TaskStatus.FAILED
            return
        if verdict.decision is ApprovalDecision.DEFER:
            state.status = TaskStatus.AWAITING_APPROVAL
            return

        tool = self.tools.get(call.tool_name)
        if tool is None:
            state.error = f"Unknown tool: {call.tool_name}"
            state.status = TaskStatus.FAILED
            return

        tool_ctx = ToolContext(
            task_id=state.id,
            session_id=state.session_id,
            workspace=str(get_settings().workspace_dir),
            scratchpad=state.scratchpad,
        )
        outcome = await tool.execute(call.arguments, tool_ctx)
        state.tool_results.append(outcome)
        state.add_event(
            "tool_result",
            {"tool": call.tool_name, "ok": outcome.ok, "error": outcome.error},
        )
        if not outcome.ok:
            # Non-fatal: surface the error but let the agent react next step.
            state.append_message(
                AgentMessage(
                    role="tool",
                    name=call.tool_name,
                    content=json.dumps({"ok": False, "error": outcome.error}),
                )
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _make_ctx(self, state: OrchestratorState) -> AgentContext:
        """Build an AgentContext from current state + memory recall."""
        from ..memory.base import MemoryQuery

        recalled = await self.memory.recall(
            MemoryQuery(
                text=state.goal,
                scope="conversation",
                session_id=str(state.session_id),
                limit=5,
            )
        )
        history = list(state.history)
        if recalled:
            history = [
                AgentMessage(role="assistant", content=r.content) for r in recalled
            ] + history
        return AgentContext(
            task_id=state.id,
            session_id=state.session_id,
            goal=state.goal,
            history=history,
            scratchpad=state.scratchpad,
        )


# ---------------------------------------------------------------------------
# Helpers (module-level for testability)
# ---------------------------------------------------------------------------
def _parse_plan(raw: str, goal: str) -> TaskPlan:
    """Best-effort parse of an LLM plan message into a :class:`TaskPlan`.

    Accepts the JSON shape emitted by ``MockLLMClient`` and by the Phase 2
    planner prompt. Falls back to a single-step plan on any parse failure so
    the orchestrator never hard-stops on a malformed model output.
    """
    from ..config.schemas import TaskStep

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return TaskPlan(
            goal=goal, steps=[TaskStep(description=goal, assigned_agent=AgentRole.OFFICE)]
        )

    steps: list[TaskStep] = []
    for raw_step in payload.get("steps", []):
        try:
            role = AgentRole(raw_step.get("assigned_agent", "office"))
        except ValueError:
            role = AgentRole.OFFICE
        steps.append(
            TaskStep(
                description=str(raw_step.get("description", "")),
                assigned_agent=role,
                tool_hints=list(raw_step.get("tool_hints", [])),
                expected_risk=raw_step.get("expected_risk", "none"),
            )
        )
    if not steps:
        steps.append(TaskStep(description=goal, assigned_agent=AgentRole.OFFICE))
    return TaskPlan(goal=goal, steps=steps, notes=str(payload.get("notes", "")))


async def _persist_memory(memory: MemoryStore, state: OrchestratorState) -> None:
    """Write the final assistant message (if any) to conversation memory."""
    if not state.history:
        return
    last = state.history[-1]
    await memory.append(
        MemoryRecord(
            scope="conversation",
            kind="chat",
            content=last.content,
            session_id=str(state.session_id),
            metadata={"task_id": str(state.id), "status": state.status.value},
        )
    )


# ---------------------------------------------------------------------------
# Process-wide accessor
# ---------------------------------------------------------------------------
_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    """Return the shared orchestrator (lazy, no agents registered by default)."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator


def reset_orchestrator() -> None:
    """Reset the singleton (tests)."""
    global _orchestrator
    _orchestrator = None
