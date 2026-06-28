"""LangGraph orchestrator end-to-end tests.

These exercise the real ``StateGraph``: plan -> execute -> review with
conditional edges, verifying the graph compiles, runs, and routes correctly
on pass / replan / fail verdicts. Uses the mock LLM so no network is needed.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from rabeeh_core.agents.planner import PlannerAgent
from rabeeh_core.agents.reviewer import ReviewerAgent
from rabeeh_core.config.schemas import TaskStatus
from rabeeh_core.llm.mock import MockLLMClient
from rabeeh_core.orchestration.graph import GraphOrchestrator
from rabeeh_core.orchestration.runner import Orchestrator
from rabeeh_core.tools.registry import get_registry


def _build_graph(llm: MockLLMClient) -> GraphOrchestrator:
    """Wire a graph orchestrator against the mock LLM + default tools."""
    return GraphOrchestrator(
        llm=llm,
        tools=get_registry(),
        planner=PlannerAgent(llm),
        reviewer=ReviewerAgent(llm),
    )


def _plan_json(*roles: str) -> str:
    """Helper: emit a plan JSON with one step per role."""
    return json.dumps(
        {
            "goal": "g",
            "steps": [
                {"description": f"step {i}", "assigned_agent": r, "expected_risk": "none"}
                for i, r in enumerate(roles)
            ],
        }
    )


@pytest.mark.asyncio
async def test_graph_runs_single_step_to_completion() -> None:
    """Plan(1 step) -> execute -> review(pass) -> finish => COMPLETED."""
    llm = MockLLMClient()
    # planner plan, reviewer verdict
    llm.script(_plan_json("office"), json.dumps({"verdict": "pass", "reason": "ok"}))

    graph = _build_graph(llm)
    state = await graph.run("do one thing", session_id=uuid4())

    assert state.status is TaskStatus.COMPLETED
    kinds = [e.kind for e in state.events]
    assert "task_started" in kinds
    # A review event must have been recorded.
    assert any(k == "review" for k in kinds)


@pytest.mark.asyncio
async def test_graph_replans_on_replan_verdict() -> None:
    """A 'replan' verdict routes back to plan before finishing.

    The reviewer runs after EVERY step, and a replan re-runs the planner, so
    the scripted queue is consumed in a non-obvious order. We therefore feed
    an initial 'replan' verdict, then a generous supply of 'pass' verdicts so
    the run completes regardless of how many review nodes fire.
    """
    llm = MockLLMClient()
    # plan #1, then verdicts: first review replans, all subsequent pass.
    llm.script(
        _plan_json("office"),
        json.dumps({"verdict": "replan", "reason": "add a step", "fix_hint": "x"}),
        _plan_json("office", "reviewer"),  # plan #2 after replan
    )
    # Pad with 'pass' verdicts for every subsequent review node.
    for _ in range(10):
        llm.script(json.dumps({"verdict": "pass", "reason": "ok"}))

    graph = _build_graph(llm)
    state = await graph.run("needs replanning", session_id=uuid4())

    kinds = [e.kind for e in state.events]
    # At least 2 reviews ran (replan + pass).
    assert kinds.count("review") >= 2
    assert state.status is TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_graph_finishes_on_repeated_review_fail() -> None:
    """Two consecutive 'fail' verdicts must end the run as FAILED."""
    llm = MockLLMClient()
    llm.script(
        _plan_json("office"),
        json.dumps({"verdict": "fail", "reason": "bad"}),  # 1st fail -> retry
        json.dumps({"verdict": "fail", "reason": "bad"}),  # 2nd fail -> finish
    )

    graph = _build_graph(llm)
    state = await graph.run("doomed step", session_id=uuid4())

    assert state.status is TaskStatus.FAILED
    assert any(e.kind == "step_failed_review" for e in state.events)


def test_graph_falls_back_to_simple_runner_without_agents() -> None:
    """The simple Orchestrator must still work standalone (parity check)."""
    llm = MockLLMClient()
    llm.script(_plan_json("office"))
    orch = Orchestrator(
        llm=llm,
        tools=get_registry(),
    )
    # No agents registered for 'office' -> synthesised/fallback path still
    # completes without raising.
    import asyncio

    state = asyncio.run(orch.run("smoke", session_id=uuid4()))
    assert state.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}
