"""Phase 4 tests — code tool, coding agent, research agent."""

from __future__ import annotations

from uuid import uuid4

import pytest

from rabeeh_core.agents.base import AgentContext
from rabeeh_core.agents.coding import CodingAgent, _strip_fences, classify_run_result
from rabeeh_core.agents.research import ResearchAgent
from rabeeh_core.config.schemas import AgentRole, RiskLevel
from rabeeh_core.llm.mock import MockLLMClient
from rabeeh_core.tools.base import ToolContext
from rabeeh_core.tools.code import RunCodeTool


def _ctx(goal: str = "do X") -> AgentContext:
    return AgentContext(task_id=uuid4(), session_id=uuid4(), goal=goal)


def _tool_ctx(workspace: str) -> ToolContext:
    return ToolContext(task_id=uuid4(), session_id=uuid4(), workspace=workspace)


# ===========================================================================
# code.run tool — real subprocess execution
# ===========================================================================
@pytest.mark.asyncio
async def test_run_code_executes_successfully(tmp_path) -> None:
    """A valid script must run and return captured stdout."""
    script = tmp_path / "hello.py"
    script.write_text('print("hello from script")', encoding="utf-8")
    tool = RunCodeTool()
    out = await tool.execute({"path": "hello.py"}, _tool_ctx(str(tmp_path)))
    assert out.ok
    assert out.data["exit_code"] == 0
    assert "hello from script" in out.data["stdout"]


@pytest.mark.asyncio
async def test_run_code_captures_stderr_on_failure(tmp_path) -> None:
    """A script that raises must report exit_code != 0 and stderr content."""
    script = tmp_path / "bad.py"
    script.write_text('raise ValueError("boom")', encoding="utf-8")
    tool = RunCodeTool()
    out = await tool.execute({"path": "bad.py"}, _tool_ctx(str(tmp_path)))
    assert not out.ok
    assert out.data["exit_code"] != 0
    assert "boom" in out.data["stderr"]


@pytest.mark.asyncio
async def test_run_code_times_out(tmp_path) -> None:
    """An infinite loop must be killed by the timeout."""
    script = tmp_path / "loop.py"
    script.write_text("while True:\n    pass", encoding="utf-8")
    tool = RunCodeTool()
    out = await tool.execute({"path": "loop.py", "timeout": 2}, _tool_ctx(str(tmp_path)))
    assert not out.ok
    assert "timed out" in (out.error or "")


@pytest.mark.asyncio
async def test_run_code_missing_script(tmp_path) -> None:
    tool = RunCodeTool()
    out = await tool.execute({"path": "nope.py"}, _tool_ctx(str(tmp_path)))
    assert not out.ok and "not found" in (out.error or "").lower()


def test_run_code_risk_is_destructive() -> None:
    assert RunCodeTool.risk is RiskLevel.DESTRUCTIVE


# ===========================================================================
# Coding agent state machine
# ===========================================================================
def test_strip_fences_removes_markdown() -> None:
    assert _strip_fences("```python\nprint(1)\n```").strip() == "print(1)"
    assert _strip_fences("print(1)").strip() == "print(1)"


def test_classify_run_result_success() -> None:
    assert classify_run_result({"exit_code": 0}) == "done"


def test_classify_run_result_failure() -> None:
    assert classify_run_result({"exit_code": 1}) == "fix"


@pytest.mark.asyncio
async def test_coding_agent_generates_then_proposes_write() -> None:
    """First step: LLM generates code -> agent proposes file.write."""
    llm = MockLLMClient()
    llm.script("print('generated')")
    agent = CodingAgent(llm=llm)
    ctx = _ctx("write a hello world script")
    ctx.scratchpad["step"] = "write a hello world script"
    result = await agent.run(ctx)
    assert result.tool_call is not None
    assert result.tool_call.tool_name == "file.write"
    assert "generated" in result.tool_call.arguments["content"]
    # Phase should advance to 'run'.
    assert ctx.scratchpad["coding_phase"] == "run"


@pytest.mark.asyncio
async def test_coding_agent_run_phase_proposes_code_run() -> None:
    """Second step: agent proposes code.run on the written script."""
    llm = MockLLMClient()
    agent = CodingAgent(llm=llm)
    ctx = _ctx()
    ctx.scratchpad["coding_phase"] = "run"
    ctx.scratchpad["coding_script"] = "gen/x.py"
    result = await agent.run(ctx)
    assert result.tool_call is not None
    assert result.tool_call.tool_name == "code.run"
    assert result.tool_call.arguments["path"] == "gen/x.py"


@pytest.mark.asyncio
async def test_coding_agent_gives_up_after_max_fixes() -> None:
    """After max_fixes attempts, the agent must signal done."""
    llm = MockLLMClient()
    agent = CodingAgent(llm=llm, max_fixes=2)
    ctx = _ctx()
    ctx.scratchpad["coding_phase"] = "fix"
    ctx.scratchpad["coding_fix_attempts"] = 2
    result = await agent.run(ctx)
    assert result.done is True


def test_coding_agent_role() -> None:
    assert CodingAgent.role is AgentRole.CODING


# ===========================================================================
# Research agent decision logic
# ===========================================================================
@pytest.mark.asyncio
async def test_research_first_step_always_searches() -> None:
    """The first research step must propose a web.search, not fetch."""
    llm = MockLLMClient()
    agent = ResearchAgent(llm=llm)
    ctx = _ctx("latest AI news")
    result = await agent.run(ctx)
    assert result.tool_call is not None
    assert result.tool_call.tool_name == "web.search"
    assert result.tool_call.arguments["query"] == "latest AI news"


@pytest.mark.asyncio
async def test_research_uses_llm_decision_for_subsequent_steps() -> None:
    """After the first search, the agent must defer to the LLM's decision."""
    llm = MockLLMClient()
    llm.script("FETCH: https://example.com/article")
    agent = ResearchAgent(llm=llm)
    ctx = _ctx("topic")
    ctx.scratchpad["research_round"] = 1
    result = await agent.run(ctx)
    assert result.tool_call is not None
    assert result.tool_call.tool_name == "web.fetch"
    assert "example.com" in result.tool_call.arguments["url"]


@pytest.mark.asyncio
async def test_research_done_decision_finishes() -> None:
    """A DONE decision must set done=True and carry the briefing."""
    llm = MockLLMClient()
    llm.script("DONE: Here is the summary of findings.")
    agent = ResearchAgent(llm=llm)
    ctx = _ctx("topic")
    ctx.scratchpad["research_round"] = 2
    result = await agent.run(ctx)
    assert result.done is True
    assert "summary of findings" in (result.message or "")


@pytest.mark.asyncio
async def test_research_forces_done_at_max_steps() -> None:
    """At the step cap, the agent must finish even with an unparseable reply."""
    llm = MockLLMClient()
    llm.script("some unstructured text without a keyword")
    agent = ResearchAgent(llm=llm, max_steps=2)
    ctx = _ctx("topic")
    ctx.scratchpad["research_round"] = 2
    result = await agent.run(ctx)
    assert result.done is True
    assert "max steps" in (result.message or "").lower()


def test_research_agent_role() -> None:
    assert ResearchAgent.role is AgentRole.RESEARCH
