from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from rabeeh_core.agents.base import AgentContext
from rabeeh_core.agents.memory_agent import MemoryAgent
from rabeeh_core.config.schemas import AgentRole
from rabeeh_core.memory.base import MemoryQuery, MemoryRecord


def _mock_memory() -> AsyncMock:
    m = AsyncMock()
    m.remember = AsyncMock()
    m.search = AsyncMock(return_value=[])
    m.get_history = AsyncMock(return_value=[])
    m.learn = AsyncMock()
    m.ask = AsyncMock(return_value=[])
    m.clear_session = AsyncMock()
    m.recall = AsyncMock(return_value=[])
    return m


@pytest.fixture
def ctx() -> AgentContext:
    return AgentContext(
        task_id=uuid4(),
        session_id=uuid4(),
        goal="test",
    )


class TestMemoryAgent:
    def test_role_and_description(self) -> None:
        agent = MemoryAgent(_mock_memory())
        assert agent.role is AgentRole.MEMORY
        assert agent.description

    def test_system_prompt(self) -> None:
        agent = MemoryAgent(_mock_memory())
        prompt = agent.system_prompt()
        assert "Memory Agent" in prompt

    @pytest.mark.asyncio
    async def test_remember(self, ctx: AgentContext) -> None:
        memory = _mock_memory()
        agent = MemoryAgent(memory)
        ctx.goal = "remember This is an important fact"
        result = await agent.run(ctx)
        assert result.done
        memory.remember.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_remember_empty(self, ctx: AgentContext) -> None:
        agent = MemoryAgent(_mock_memory())
        ctx.goal = "remember"
        result = await agent.run(ctx)
        assert result.done
        assert "Nothing to remember" in result.message

    @pytest.mark.asyncio
    async def test_search(self, ctx: AgentContext) -> None:
        memory = _mock_memory()
        agent = MemoryAgent(memory)
        ctx.goal = "search test query"
        result = await agent.run(ctx)
        assert result.done
        memory.search.assert_awaited_once_with("test query", top_k=5)

    @pytest.mark.asyncio
    async def test_search_with_results(self, ctx: AgentContext) -> None:
        memory = _mock_memory()
        memory.search.return_value = [
            MemoryRecord(id="1", content="result 1", kind="chat", score=0.95),
            MemoryRecord(id="2", content="result 2", kind="chat", score=0.85),
        ]
        agent = MemoryAgent(memory)
        ctx.goal = "search something"
        result = await agent.run(ctx)
        assert result.done
        assert "Search results" in result.message

    @pytest.mark.asyncio
    async def test_search_empty(self, ctx: AgentContext) -> None:
        agent = MemoryAgent(_mock_memory())
        ctx.goal = "search"
        result = await agent.run(ctx)
        assert result.done
        assert "empty" in result.message

    @pytest.mark.asyncio
    async def test_history(self, ctx: AgentContext) -> None:
        memory = _mock_memory()
        agent = MemoryAgent(memory)
        ctx.goal = "history"
        result = await agent.run(ctx)
        assert result.done
        memory.get_history.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_history_with_results(self, ctx: AgentContext) -> None:
        memory = _mock_memory()
        memory.get_history.return_value = [
            MemoryRecord(id="1", content="hello", kind="chat"),
        ]
        agent = MemoryAgent(memory)
        ctx.goal = "history"
        result = await agent.run(ctx)
        assert result.done
        assert "History for" in result.message

    @pytest.mark.asyncio
    async def test_learn(self, ctx: AgentContext) -> None:
        memory = _mock_memory()
        agent = MemoryAgent(memory)
        ctx.goal = "learn Python | is | programming language"
        result = await agent.run(ctx)
        assert result.done
        assert "Learned" in result.message
        memory.learn.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_learn_invalid(self, ctx: AgentContext) -> None:
        agent = MemoryAgent(_mock_memory())
        ctx.goal = "learn too few"
        result = await agent.run(ctx)
        assert result.done
        assert "Usage" in result.message

    @pytest.mark.asyncio
    async def test_ask(self, ctx: AgentContext) -> None:
        memory = _mock_memory()
        agent = MemoryAgent(memory)
        ctx.goal = "ask Python"
        result = await agent.run(ctx)
        assert result.done
        memory.ask.assert_awaited_once_with("Python")

    @pytest.mark.asyncio
    async def test_ask_empty(self, ctx: AgentContext) -> None:
        agent = MemoryAgent(_mock_memory())
        ctx.goal = "ask"
        result = await agent.run(ctx)
        assert result.done
        assert "No subject" in result.message

    @pytest.mark.asyncio
    async def test_clear(self, ctx: AgentContext) -> None:
        memory = _mock_memory()
        agent = MemoryAgent(memory)
        ctx.goal = "clear"
        result = await agent.run(ctx)
        assert result.done
        memory.clear_session.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_recall_default(self, ctx: AgentContext) -> None:
        memory = _mock_memory()
        agent = MemoryAgent(memory)
        ctx.goal = "what do you know about me"
        result = await agent.run(ctx)
        assert result.done
        memory.recall.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_recall_with_results(self, ctx: AgentContext) -> None:
        memory = _mock_memory()
        memory.recall.return_value = [
            MemoryRecord(id="1", content="user likes Python", kind="insight", score=0.92),
        ]
        agent = MemoryAgent(memory)
        ctx.goal = "what do you know about me"
        result = await agent.run(ctx)
        assert result.done
        assert "Relevant memories" in result.message
