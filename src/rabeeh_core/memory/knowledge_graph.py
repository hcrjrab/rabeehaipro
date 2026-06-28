"""Knowledge graph store for structured entity-relation memory.

Uses PostgreSQL when available, falling back to a local SQLite file for
development. Stores (subject, predicate, object) triples with confidence
scores and supports graph traversal up to configurable depth.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..config.settings import get_settings
from .base import KnowledgeTriple

_log = logging.getLogger(__name__)

# Try to import aiosqlite for the standalone fallback.
try:
    import aiosqlite

    _HAS_SQLITE = True
except ImportError:  # pragma: no cover
    _HAS_SQLITE = False


class SQLiteKnowledgeGraph:
    """A simple knowledge graph backed by a local SQLite file.

    Designed for development and single-user desktop use. For production,
    replace with a dedicated graph database (Neo4j, Amazon Neptune) by
    implementing the ``KnowledgeGraph`` protocol.
    """

    name: str = "sqlite_kg"

    def __init__(self, db_path: str | Path | None = None) -> None:
        settings = get_settings()
        self._db_path = Path(db_path or settings.data_dir / "knowledge_graph.db")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: aiosqlite.Connection | None = None

    async def _ensure_db(self) -> aiosqlite.Connection:
        if self._conn is None:
            if not _HAS_SQLITE:
                raise RuntimeError("aiosqlite is required for the knowledge graph.")
            self._conn = await aiosqlite.connect(str(self._db_path))
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_triples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    source TEXT DEFAULT '',
                    metadata_json TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_kg_subject
                ON knowledge_triples(subject)
            """)
            await self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_kg_object
                ON knowledge_triples(object)
            """)
            await self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_kg_predicate
                ON knowledge_triples(predicate)
            """)
            await self._conn.commit()
        return self._conn

    # ------------------------------------------------------------------
    # KnowledgeGraph protocol
    # ------------------------------------------------------------------

    async def add_triple(self, triple: KnowledgeTriple) -> None:
        conn = await self._ensure_db()
        await conn.execute(
            """INSERT INTO knowledge_triples
               (subject, predicate, object, confidence, source, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                triple.subject,
                triple.predicate,
                triple.obj,
                triple.confidence,
                triple.source,
                json.dumps(triple.metadata),
            ),
        )
        await conn.commit()
        _log.debug("KG added: (%s) --[%s]--> (%s)", triple.subject, triple.predicate, triple.obj)

    async def query(
        self,
        subject: str | None = None,
        predicate: str | None = None,
        obj: str | None = None,
        *,
        limit: int = 100,
    ) -> list[KnowledgeTriple]:
        conn = await self._ensure_db()
        conditions = []
        params: list[Any] = []
        if subject:
            conditions.append("subject = ?")
            params.append(subject)
        if predicate:
            conditions.append("predicate = ?")
            params.append(predicate)
        if obj:
            conditions.append("object = ?")
            params.append(obj)

        where = " AND ".join(conditions) if conditions else "1=1"
        cursor = await conn.execute(
            f"""SELECT subject, predicate, object, confidence, source, metadata_json
                FROM knowledge_triples WHERE {where} ORDER BY confidence DESC LIMIT ?""",
            [*params, limit],
        )
        rows = await cursor.fetchall()
        return [
            KnowledgeTriple(
                subject=r[0],
                predicate=r[1],
                obj=r[2],
                confidence=r[3],
                source=r[4],
                metadata=json.loads(r[5]) if r[5] else {},
            )
            for r in rows
        ]

    async def delete_subject(self, subject: str) -> None:
        conn = await self._ensure_db()
        await conn.execute("DELETE FROM knowledge_triples WHERE subject = ?", (subject,))
        await conn.commit()

    async def get_related(self, entity: str, max_hops: int = 1) -> list[KnowledgeTriple]:
        """Traverse the graph from *entity* in both directions."""
        conn = await self._ensure_db()

        results: list[KnowledgeTriple] = []
        seen: set[str] = {entity}

        current = {entity}
        for _ in range(max_hops):
            if not current:
                break
            placeholders = ",".join("?" for _ in current)
            params = list(current)

            # Outgoing edges.
            cursor = await conn.execute(
                f"""SELECT subject, predicate, object, confidence, source, metadata_json
                    FROM knowledge_triples WHERE subject IN ({placeholders})
                    UNION
                    SELECT subject, predicate, object, confidence, source, metadata_json
                    FROM knowledge_triples WHERE object IN ({placeholders})""",
                [*params, *params],
            )
            rows = await cursor.fetchall()
            for r in rows:
                triple = KnowledgeTriple(
                    subject=r[0],
                    predicate=r[1],
                    obj=r[2],
                    confidence=r[3],
                    source=r[4],
                    metadata=json.loads(r[5]) if r[5] else {},
                )
                if triple.subject not in seen or triple.obj not in seen:
                    results.append(triple)
                seen.add(triple.subject)
                seen.add(triple.obj)

            # Next hop: entities discovered this round.
            new_entities = set()
            for r in rows:
                if r[0] not in seen:
                    new_entities.add(r[0])
                if r[2] not in seen:
                    new_entities.add(r[2])
            current = new_entities

        return results

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
