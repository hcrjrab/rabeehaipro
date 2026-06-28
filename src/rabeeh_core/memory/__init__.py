"""Memory systems.

Provides three tiers of memory, all accessible through the composite
``MemoryService``:

1. **Conversation memory** (``MemoryStore``) — short-term chat history.
   - ``InMemoryStore`` — thread-safe in-process (dev/tests).
   - ``PostgresMemoryStore`` — durable PostgreSQL (production).

2. **Vector memory** (``VectorMemoryStore``) — semantic/embedding search.
   - ``ChromaMemoryStore`` — ChromaDB persistent client.

3. **Knowledge graph** (``KnowledgeGraph``) — structured entity relations.
   - ``SQLiteKnowledgeGraph`` — local SQLite-backed (dev).
   - Extensible to Neo4j/Neptune for production.

The ``MemoryService`` composite routes operations to the appropriate
backend automatically.
"""

from __future__ import annotations

from .base import (
    KnowledgeGraph,
    KnowledgeTriple,
    MemoryKind,
    MemoryQuery,
    MemoryRecord,
    MemoryScope,
    MemoryService,
    MemoryStore,
    VectorMemoryStore,
)
from .chroma_store import CHROMA_ENABLED, ChromaMemoryStore
from .in_memory import InMemoryStore
from .knowledge_graph import SQLiteKnowledgeGraph
from .postgres_store import PostgresMemoryStore

__all__ = [
    "CHROMA_ENABLED",
    "ChromaMemoryStore",
    "InMemoryStore",
    "KnowledgeGraph",
    "KnowledgeTriple",
    "MemoryKind",
    "MemoryQuery",
    "MemoryRecord",
    "MemoryScope",
    "MemoryService",
    "MemoryStore",
    "PostgresMemoryStore",
    "SQLiteKnowledgeGraph",
    "VectorMemoryStore",
]
