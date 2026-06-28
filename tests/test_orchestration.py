"""Memory store tests (in-process implementation)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from rabeeh_core.memory import InMemoryStore
from rabeeh_core.memory.base import MemoryQuery, MemoryRecord


@pytest.mark.asyncio
async def test_append_and_recent_roundtrip() -> None:
    """Appended records must be retrievable in chronological order."""
    store = InMemoryStore()
    sid = str(uuid4())
    await store.append(MemoryRecord(scope="conversation", session_id=sid, content="first"))
    await store.append(MemoryRecord(scope="conversation", session_id=sid, content="second"))

    recent = await store.recent(scope="conversation", session_id=sid)
    assert [r.content for r in recent] == ["first", "second"]


@pytest.mark.asyncio
async def test_recent_is_session_scoped() -> None:
    """Records from another session must not leak into the query."""
    store = InMemoryStore()
    a, b = str(uuid4()), str(uuid4())
    await store.append(MemoryRecord(scope="conversation", session_id=a, content="a1"))
    await store.append(MemoryRecord(scope="conversation", session_id=b, content="b1"))

    got = await store.recent(scope="conversation", session_id=a)
    assert [r.content for r in got] == ["a1"]


@pytest.mark.asyncio
async def test_recall_ranks_by_token_overlap() -> None:
    """Recall must surface the most lexically-relevant record first."""
    store = InMemoryStore()
    sid = str(uuid4())
    await store.append(
        MemoryRecord(scope="long_term", session_id=sid, content="The cat sat on the mat")
    )
    await store.append(
        MemoryRecord(scope="long_term", session_id=sid, content="Invoice totals and tax lines")
    )
    await store.append(MemoryRecord(scope="long_term", session_id=sid, content="cat food bowl"))

    hits = await store.recall(MemoryQuery(text="cat mat", scope="long_term"))
    assert hits, "expected at least one recall hit"
    assert "cat" in hits[0].content.lower()


@pytest.mark.asyncio
async def test_forget_clears_scope() -> None:
    """``forget`` must remove matching records."""
    store = InMemoryStore()
    sid = str(uuid4())
    await store.append(MemoryRecord(scope="conversation", session_id=sid, content="x"))
    await store.append(MemoryRecord(scope="preference", session_id=sid, content="y"))

    await store.forget(scope="conversation", session_id=sid)
    assert await store.recent(scope="conversation", session_id=sid) == []
    assert await store.recent(scope="preference", session_id=sid)  # untouched
