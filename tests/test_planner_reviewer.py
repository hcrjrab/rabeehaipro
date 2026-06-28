"""Planner + Reviewer agent tests."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from rabeeh_core.agents.base import AgentContext
from rabeeh_core.agents.planner import PlannerAgent, _parse_plan_json
from rabeeh_core.agents.reviewer import ReviewerAgent, _parse_review
from rabeeh_core.config.schemas import AgentRole
from rabeeh_core.llm.mock import MockLLMClient


def _ctx(goal: str = "do X") -> AgentContext:
    return AgentContext(task_id=uuid4(), session_id=uuid4(), goal=goal)


# ---------------------------------------------------------------------------
# Planner parsing
# ---------------------------------------------------------------------------
def test_parse_plan_json_valid() -> None:
    """A well-formed plan JSON must parse into typed steps."""
    raw = json.dumps(
        {
            "goal": "g",
            "steps": [
                {
                    "description": "Research it",
                    "assigned_agent": "research",
                    "expected_risk": "none",
                },
                {"description": "Write it", "assigned_agent": "office", "expected_risk": "safe"},
            ],
            "notes": "n",
        }
    )
    plan = _parse_plan_json(raw, "g")
    assert [s.assigned_agent for s in plan.steps] == [AgentRole.RESEARCH, AgentRole.OFFICE]
    assert plan.notes == "n"


def test_parse_plan_json_strips_markdown_fences() -> None:
    """Fenced JSON (```json ... ```) must be tolerated."""
    raw = (
        "```json\n"
        + json.dumps({"goal": "g", "steps": [{"description": "s", "assigned_agent": "office"}]})
        + "\n```"
    )
    plan = _parse_plan_json(raw, "g")
    assert len(plan.steps) == 1


def test_parse_plan_json_rejects_empty_steps() -> None:
    """An empty steps array must raise (so the planner retries)."""
    from rabeeh_core.agents.planner import _PlanParseError

    with pytest.raises(_PlanParseError):
        _parse_plan_json(json.dumps({"goal": "g", "steps": []}), "g")


def test_parse_plan_json_coerces_bad_role_to_office() -> None:
    """An unknown role string must fall back to 'office', not crash."""
    plan = _parse_plan_json(
        json.dumps({"goal": "g", "steps": [{"description": "s", "assigned_agent": "wizard"}]}), "g"
    )
    assert plan.steps[0].assigned_agent == AgentRole.OFFICE


# ---------------------------------------------------------------------------
# Planner agent behaviour
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_planner_parses_model_output_into_plan() -> None:
    """A valid model plan must round-trip into the AgentResult.extra."""
    llm = MockLLMClient()
    llm.script(
        json.dumps(
            {
                "goal": "build a quote",
                "steps": [
                    {"description": "Gather requirements", "assigned_agent": "research"},
                    {"description": "Generate quote", "assigned_agent": "business"},
                    {"description": "Review", "assigned_agent": "reviewer"},
                ],
            }
        )
    )
    agent = PlannerAgent(llm=llm)
    result = await agent.run(_ctx("build a quote"))
    assert "plan" in result.extra
    assert len(result.extra["plan"]["steps"]) == 3
    assert result.extra.get("fallback") is None


@pytest.mark.asyncio
async def test_planner_retries_then_falls_back_on_garbage() -> None:
    """Persistently malformed output must yield a single-step fallback plan."""
    llm = MockLLMClient()
    llm.script("not json", "still not json")  # both attempts fail
    agent = PlannerAgent(llm=llm, max_attempts=2)
    result = await agent.run(_ctx("do something"))
    assert result.extra.get("fallback") is True
    assert len(result.extra["plan"]["steps"]) == 1


@pytest.mark.asyncio
async def test_planner_recovers_on_second_attempt() -> None:
    """One bad response then a good one must succeed (retry works)."""
    llm = MockLLMClient()
    llm.script(
        "garbage",
        json.dumps({"goal": "g", "steps": [{"description": "ok", "assigned_agent": "office"}]}),
    )
    agent = PlannerAgent(llm=llm, max_attempts=2)
    result = await agent.run(_ctx("g"))
    assert result.extra.get("attempts") == 2
    assert result.extra.get("fallback") is None


# ---------------------------------------------------------------------------
# Reviewer parsing + behaviour
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        (json.dumps({"verdict": "pass", "reason": "looks good"}), "pass"),
        (json.dumps({"verdict": "fail", "reason": "missing output"}), "fail"),
        (json.dumps({"verdict": "replan", "reason": "wrong approach"}), "replan"),
        ("```json\n" + json.dumps({"verdict": "pass"}) + "\n```", "pass"),
    ],
)
def test_parse_review_valid(raw: str, expected: str) -> None:
    verdict, reason, _ = _parse_review(raw)
    assert verdict == expected


def test_parse_review_falls_back_to_regex() -> None:
    """A verdict wrapped in prose must still be extracted."""
    verdict, _, _ = _parse_review('I checked it. {"verdict": "pass"} done.')
    assert verdict == "pass"


def test_parse_review_returns_none_on_total_failure() -> None:
    """Genuinely unparseable input must return None so the agent retries."""
    verdict, _, _ = _parse_review("the weather is nice")
    assert verdict is None


@pytest.mark.asyncio
async def test_reviewer_passes_on_clean_evidence() -> None:
    """A 'pass' verdict must set ``done`` on the AgentResult."""
    llm = MockLLMClient()
    llm.script(json.dumps({"verdict": "pass", "reason": "ok"}))
    agent = ReviewerAgent(llm=llm)
    result = await agent.run(_ctx())
    assert result.extra["verdict"] == "pass"
    assert result.done is True


@pytest.mark.asyncio
async def test_reviewer_can_request_replan() -> None:
    """A 'replan' verdict must NOT mark done and must carry a fix_hint."""
    llm = MockLLMClient()
    llm.script(json.dumps({"verdict": "replan", "reason": "r", "fix_hint": "add a step"}))
    agent = ReviewerAgent(llm=llm)
    result = await agent.run(_ctx())
    assert result.extra["verdict"] == "replan"
    assert result.done is False
    assert result.extra["fix_hint"] == "add a step"
