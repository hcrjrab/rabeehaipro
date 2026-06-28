"""Memory store abstractions.

Defines the ``MemoryStore`` Protocol that every memory backend satisfies,
plus the ``VectorMemoryStore`` and ``KnowledgeGraph`` protocols for
specialised stores.

The orchestrator uses all three protocol types via a composite "memory
service" that routes reads/writes to the appropriate store based on the
scope and nature of the data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

# ---------------------------------------------------------------------------
# Common types
# ---------------------------------------------------------------------------

MemoryScope = str  # "conversation" | "project" | "long_term" | "preference"

MemoryKind = str  # "chat" | "tool_result" | "plan" | "error" | "insight"


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class MemoryRecord:
    """A single memory entry, independent of storage backend."""

    id: UUID = field(default_factory=uuid4)
    scope: MemoryScope = "conversation"
    kind: MemoryKind = "chat"
    content: str = ""
    session_id: str = ""
    project_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None
    created_at: datetime = field(default_factory=_utcnow)
    score: float = 0.0  # relevance score set by retrieval


@dataclass(slots=True)
class MemoryQuery:
    """Structured query for memory retrieval."""

    text: str = ""
    scope: MemoryScope | None = None
    kind: MemoryKind | None = None
    session_id: str | None = None
    project_id: str | None = None
    limit: int = 10
    min_score: float = 0.0
    include_embeddings: bool = False


# ---------------------------------------------------------------------------
# Core MemoryStore (conversational / key-value)
# ---------------------------------------------------------------------------


class MemoryStore(Protocol):
    """Key-value / conversation memory protocol.

    Used for short-term conversation history, preferences, and simple
    key-value lookups.
    """

    async def append(self, record: MemoryRecord) -> None:
        """Store a single memory record."""
        ...

    async def recent(
        self,
        scope: MemoryScope,
        session_id: str,
        *,
        limit: int = 20,
        kind: MemoryKind | None = None,
    ) -> list[MemoryRecord]:
        """Return the most recent records for a scope + session."""
        ...

    async def recall(
        self,
        query: MemoryQuery,
    ) -> list[MemoryRecord]:
        """Search records by text similarity / metadata filters."""
        ...

    async def forget(
        self,
        scope: MemoryScope,
        session_id: str,
    ) -> None:
        """Delete all records for a scope + session."""
        ...


# ---------------------------------------------------------------------------
# Vector memory (semantic / embedding search)
# ---------------------------------------------------------------------------


class VectorMemoryStore(Protocol):
    """Semantic memory backed by vector embeddings.

    Allows similarity search across all memory scopes using embedding-based
    retrieval.
    """

    async def add_document(
        self,
        content: str,
        *,
        scope: MemoryScope = "long_term",
        kind: MemoryKind = "insight",
        metadata: dict[str, Any] | None = None,
        embedding: list[float] | None = None,
    ) -> str:
        """Add a document to the vector store. Returns the document ID."""
        ...

    async def similarity_search(
        self,
        query: str,
        *,
        top_k: int = 10,
        scope: MemoryScope | None = None,
        score_threshold: float = 0.0,
    ) -> list[MemoryRecord]:
        """Search by semantic similarity to *query* text."""
        ...

    async def delete_document(self, doc_id: str) -> None:
        """Remove a document from the store."""
        ...

    async def count(self) -> int:
        """Return the total number of documents in the store."""
        ...


# ---------------------------------------------------------------------------
# Knowledge graph
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class KnowledgeTriple:
    """A (subject, predicate, object) triple in the knowledge graph."""

    subject: str
    predicate: str
    obj: str  # "object" is a Python builtin
    confidence: float = 1.0
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class KnowledgeGraph(Protocol):
    """Structured knowledge store using a property graph model.

    Enables reasoning about entities and their relationships.
    """

    async def add_triple(self, triple: KnowledgeTriple) -> None:
        """Insert a (subject, predicate, object) triple."""
        ...

    async def query(
        self,
        subject: str | None = None,
        predicate: str | None = None,
        obj: str | None = None,
        *,
        limit: int = 100,
    ) -> list[KnowledgeTriple]:
        """Query triples by any combination of S/P/O."""
        ...

    async def delete_subject(self, subject: str) -> None:
        """Remove all triples for a given subject."""
        ...

    async def get_related(self, entity: str, max_hops: int = 1) -> list[KnowledgeTriple]:
        """Traverse the graph from *entity* and return connected triples."""
        ...


# ---------------------------------------------------------------------------
# Composite memory service
# ---------------------------------------------------------------------------


class MemoryService:
    """High-level memory service that coordinates all memory backends.

    Routes operations to the appropriate store based on scope and data type.
    This is the single entry point that agents and the orchestrator use.
    """

    def __init__(
        self,
        conversation_store: MemoryStore,
        vector_store: VectorMemoryStore | None = None,
        knowledge_graph: KnowledgeGraph | None = None,
    ) -> None:
        self._conversation = conversation_store
        self._vector = vector_store
        self._graph = knowledge_graph

    # -- Conversation ------------------------------------------------------

    async def add_message(
        self,
        role: str,
        content: str,
        *,
        session_id: str = "",
        project_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a chat message to conversation memory."""
        await self._conversation.append(
            MemoryRecord(
                scope="conversation",
                kind="chat",
                content=content,
                session_id=session_id,
                project_id=project_id,
                metadata={"role": role, **(metadata or {})},
            )
        )

    async def get_history(
        self,
        session_id: str,
        *,
        limit: int = 50,
    ) -> list[MemoryRecord]:
        """Retrieve recent conversation history."""
        return await self._conversation.recent(
            "conversation",
            session_id,
            limit=limit,
            kind="chat",
        )

    async def recall(self, query: MemoryQuery) -> list[MemoryRecord]:
        """General-purpose recall across the conversation store."""
        return await self._conversation.recall(query)

    # -- Semantic / vector -------------------------------------------------

    async def remember(
        self,
        content: str,
        *,
        scope: MemoryScope = "long_term",
        kind: MemoryKind = "insight",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store content in vector memory for semantic retrieval."""
        if self._vector is not None:
            await self._vector.add_document(
                content,
                scope=scope,
                kind=kind,
                metadata=metadata,
            )

    async def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        scope: MemoryScope | None = None,
    ) -> list[MemoryRecord]:
        """Semantic search across vector memory."""
        if self._vector is None:
            return []
        return await self._vector.similarity_search(
            query,
            top_k=top_k,
            scope=scope,
        )

    # -- Knowledge graph ---------------------------------------------------

    async def learn(self, triple: KnowledgeTriple) -> None:
        """Add a fact to the knowledge graph."""
        if self._graph is not None:
            await self._graph.add_triple(triple)

    async def ask(self, subject: str) -> list[KnowledgeTriple]:
        """Retrieve all known facts about *subject*."""
        if self._graph is None:
            return []
        return await self._graph.get_related(subject)

    async def clear_session(self, session_id: str) -> None:
        """Clear conversation history for a session."""
        await self._conversation.forget("conversation", session_id)
