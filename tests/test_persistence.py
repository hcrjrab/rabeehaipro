"""Persistence layer tests: real async SQLite path + in-memory fallback."""

from __future__ import annotations

from uuid import uuid4

import pytest

from rabeeh_core.config.schemas import AgentMessage, TaskStatus
from rabeeh_core.orchestration.state import OrchestratorState
from rabeeh_core.persistence.db import db_available
from rabeeh_core.persistence.repository import TaskRepository


def _make_state(goal: str = "test goal") -> OrchestratorState:
    """Build a minimal orchestrator state with an event for round-trip tests."""
    state = OrchestratorState(goal=goal, session_id=uuid4())
    state.status = TaskStatus.COMPLETED
    state.add_event("task_started", {"goal": goal})
    state.add_event("task_completed", {})
    state.append_message(AgentMessage(role="assistant", content="done"))
    return state


# ---------------------------------------------------------------------------
# In-memory fallback (no DB available)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_repository_falls_back_to_in_memory_when_db_unavailable() -> None:
    """With no DB, save/get must still work via the in-memory cache."""
    repo = TaskRepository()
    state = _make_state("fallback path")
    assert db_available() is False  # no init_db() called

    await repo.save(state)
    fetched = await repo.get(state.id)
    assert fetched is not None
    assert fetched["goal"] == "fallback path"
    assert fetched["status"] == TaskStatus.COMPLETED.value
    assert len(fetched["events"]) == 2


@pytest.mark.asyncio
async def test_repository_returns_none_for_unknown_id_in_memory() -> None:
    repo = TaskRepository()
    assert await repo.get(uuid4()) is None


@pytest.mark.asyncio
async def test_repository_list_recent_in_memory_orders_newest_first() -> None:
    repo = TaskRepository()
    s1 = _make_state("first")
    s2 = _make_state("second")
    await repo.save(s1)
    await repo.save(s2)
    recent = await repo.list_recent()
    assert [t["goal"] for t in recent] == ["second", "first"]


# ---------------------------------------------------------------------------
# Real async SQLite path
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_repository_persists_to_sqlite(sqlite_db) -> None:
    """With a live SQLite DB, save/get must round-trip through the ORM."""
    assert db_available() is True
    repo = TaskRepository()
    state = _make_state("durable path")

    await repo.save(state)
    # Clear the in-memory cache to prove the read came from the DB.
    repo._cache.clear()
    fetched = await repo.get(state.id)
    assert fetched is not None
    assert fetched["goal"] == "durable path"
    assert fetched["status"] == TaskStatus.COMPLETED.value
    assert len(fetched["events"]) == 2
    assert {e["kind"] for e in fetched["events"]} == {"task_started", "task_completed"}


@pytest.mark.asyncio
async def test_repository_upsert_updates_existing_task(sqlite_db) -> None:
    """Saving the same task id twice must update, not duplicate, the row."""
    repo = TaskRepository()
    state = _make_state("v1")
    state.status = TaskStatus.RUNNING
    await repo.save(state)

    # Mutate and re-save.
    state.status = TaskStatus.COMPLETED
    state.add_event("task_completed", {})
    await repo.save(state)

    repo._cache.clear()
    fetched = await repo.get(state.id)
    assert fetched["status"] == TaskStatus.COMPLETED.value
    assert len(fetched["events"]) == 3  # 2 original + 1 added


@pytest.mark.asyncio
async def test_repository_unknown_id_returns_none_via_db(sqlite_db) -> None:
    repo = TaskRepository()
    assert await repo.get(uuid4()) is None


@pytest.mark.asyncio
async def test_repository_list_recent_via_db(sqlite_db) -> None:
    repo = TaskRepository()
    a = _make_state("a")
    b = _make_state("b")
    await repo.save(a)
    await repo.save(b)
    repo._cache.clear()
    recent = await repo.list_recent()
    assert {t["goal"] for t in recent} == {"a", "b"}
