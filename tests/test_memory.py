"""InMemoryStore and MemoryService tests."""

from __future__ import annotations

import pytest

from rabeeh_core.memory.base import (
    KnowledgeTriple,
    MemoryQuery,
    MemoryRecord,
    MemoryService,
)
from rabeeh_core.memory.in_memory import InMemoryStore


@pytest.fixture()
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture()
def service(store: InMemoryStore) -> MemoryService:
    return MemoryService(conversation_store=store)


class TestInMemoryStore:
    async def test_append_and_recent(self, store: InMemoryStore) -> None:
        await store.append(
            MemoryRecord(scope="conversation", session_id="s1", content="hello", kind="chat")
        )
        await store.append(
            MemoryRecord(scope="conversation", session_id="s1", content="world", kind="chat")
        )
        records = await store.recent("conversation", "s1")
        assert len(records) == 2
        assert records[0].content == "hello"
        assert records[1].content == "world"

    async def test_recent_with_kind_filter(self, store: InMemoryStore) -> None:
        await store.append(
            MemoryRecord(scope="conversation", session_id="s1", content="chat msg", kind="chat")
        )
        await store.append(
            MemoryRecord(
                scope="conversation", session_id="s1", content="tool result", kind="tool_result"
            )
        )
        records = await store.recent("conversation", "s1", kind="chat")
        assert len(records) == 1
        assert records[0].content == "chat msg"

    async def test_recent_orders_by_time(self, store: InMemoryStore) -> None:
        import datetime

        r1 = MemoryRecord(scope="conversation", session_id="s1", content="first", kind="chat")
        r2 = MemoryRecord(scope="conversation", session_id="s1", content="second", kind="chat")
        r1.created_at = datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC)
        r2.created_at = datetime.datetime(2024, 1, 2, tzinfo=datetime.UTC)
        await store.append(r1)
        await store.append(r2)
        records = await store.recent("conversation", "s1")
        assert len(records) == 2
        assert records[0].content == "first"
        assert records[1].content == "second"

    async def test_recent_limit(self, store: InMemoryStore) -> None:
        for i in range(5):
            await store.append(
                MemoryRecord(scope="conversation", session_id="s1", content=f"msg{i}", kind="chat")
            )
        records = await store.recent("conversation", "s1", limit=2)
        assert len(records) == 2

    async def test_recall_by_text_match(self, store: InMemoryStore) -> None:
        await store.append(
            MemoryRecord(
                scope="conversation", session_id="s1", content="the quick brown fox", kind="chat"
            )
        )
        await store.append(
            MemoryRecord(
                scope="conversation",
                session_id="s1",
                content="jumps over the lazy dog",
                kind="chat",
            )
        )
        query = MemoryQuery(text="quick fox", session_id="s1", scope="conversation", min_score=0.3)
        results = await store.recall(query)
        assert len(results) >= 1
        assert "quick" in results[0].content

    async def test_recall_empty_query_returns_recent(self, store: InMemoryStore) -> None:
        await store.append(
            MemoryRecord(scope="conversation", session_id="s1", content="test", kind="chat")
        )
        results = await store.recall(MemoryQuery(session_id="s1", scope="conversation"))
        assert len(results) == 1

    async def test_recall_no_match(self, store: InMemoryStore) -> None:
        await store.append(
            MemoryRecord(scope="conversation", session_id="s1", content="aaaaa", kind="chat")
        )
        query = MemoryQuery(text="zzzzz", session_id="s1", scope="conversation", min_score=0.5)
        results = await store.recall(query)
        assert len(results) == 0

    async def test_recall_filters_by_scope_and_kind(self, store: InMemoryStore) -> None:
        await store.append(
            MemoryRecord(scope="project", session_id="s1", content="project data", kind="insight")
        )
        await store.append(
            MemoryRecord(scope="conversation", session_id="s1", content="chat data", kind="chat")
        )
        query = MemoryQuery(text="data", scope="project", session_id="s1")
        results = await store.recall(query)
        assert all(r.scope == "project" for r in results)

    async def test_forget_clears_session(self, store: InMemoryStore) -> None:
        await store.append(
            MemoryRecord(scope="conversation", session_id="s1", content="keep me", kind="chat")
        )
        await store.append(
            MemoryRecord(scope="conversation", session_id="s2", content="keep me too", kind="chat")
        )
        await store.forget("conversation", "s1")
        assert len(list(store)) == 1

    async def test_forget_other_scope_untouched(self, store: InMemoryStore) -> None:
        await store.append(
            MemoryRecord(scope="conversation", session_id="s1", content="chat", kind="chat")
        )
        await store.append(
            MemoryRecord(scope="project", session_id="s1", content="proj", kind="insight")
        )
        await store.forget("conversation", "s1")
        remaining = list(store)
        assert len(remaining) == 1
        assert remaining[0].scope == "project"

    async def test_iter_empty(self, store: InMemoryStore) -> None:
        assert list(store) == []

    async def test_iter_returns_snapshot(self, store: InMemoryStore) -> None:
        await store.append(
            MemoryRecord(scope="conversation", session_id="s1", content="a", kind="chat")
        )
        it = iter(store)
        await store.append(
            MemoryRecord(scope="conversation", session_id="s1", content="b", kind="chat")
        )
        assert len(list(it)) == 1


class TestMemoryService:
    async def test_add_message_and_get_history(self, service: MemoryService) -> None:
        await service.add_message("user", "Hello", session_id="s1")
        await service.add_message("assistant", "Hi there", session_id="s1")
        history = await service.get_history("s1")
        assert len(history) == 2
        assert history[0].content == "Hello"
        assert history[1].content == "Hi there"

    async def test_get_history_empty(self, service: MemoryService) -> None:
        history = await service.get_history("nonexistent")
        assert history == []

    async def test_get_history_limit(self, service: MemoryService) -> None:
        for i in range(5):
            await service.add_message("user", f"msg{i}", session_id="s1")
        history = await service.get_history("s1", limit=2)
        assert len(history) == 2

    async def test_recall_delegates_to_conversation_store(self, service: MemoryService) -> None:
        await service.add_message("user", "remember this detail", session_id="s1")
        query = MemoryQuery(text="detail", session_id="s1")
        results = await service.recall(query)
        assert len(results) >= 1

    async def test_clear_session(self, service: MemoryService) -> None:
        await service.add_message("user", "temp", session_id="s1")
        await service.clear_session("s1")
        history = await service.get_history("s1")
        assert history == []

    async def test_remember_no_vector_store(self, service: MemoryService) -> None:
        await service.remember("some insight", scope="long_term", kind="insight")

    async def test_search_no_vector_store(self, service: MemoryService) -> None:
        results = await service.search("test")
        assert results == []

    async def test_learn_no_graph(self, service: MemoryService) -> None:
        await service.learn(KnowledgeTriple(subject="A", predicate="is", obj="B"))

    async def test_ask_no_graph(self, service: MemoryService) -> None:
        results = await service.ask("test")
        assert results == []

    async def test_add_message_with_metadata(self, service: MemoryService) -> None:
        await service.add_message("user", "data", session_id="s1", metadata={"key": "val"})
        history = await service.get_history("s1")
        assert history[0].metadata.get("key") == "val"

    async def test_add_message_with_project_id(self, service: MemoryService) -> None:
        await service.add_message("user", "project data", session_id="s1", project_id="p1")
        history = await service.get_history("s1")
        assert history[0].project_id == "p1"
