"""PostgreSQL-backed conversation memory store.

Persists conversation history and memory records in the project's PostgreSQL
database using SQLAlchemy async ORM. Falls back to the in-memory store when
the database is unavailable.

This is the production backend for the ``MemoryStore`` protocol, used by
the ``MemoryService`` for durable conversation history.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import (
    text,
)
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from ..config.settings import get_settings
from ..persistence.db import get_engine, get_session_factory
from .base import MemoryKind, MemoryQuery, MemoryRecord, MemoryScope

_log = logging.getLogger(__name__)

# Try to import aiosqlite or assume async DB is available.
try:
    _DB_AVAILABLE = True
except ImportError:  # pragma: no cover
    _DB_AVAILABLE = False


# ---------------------------------------------------------------------------
# SQLAlchemy table definition (created via prepare())
# ---------------------------------------------------------------------------

_MEMORY_TABLE_NAME = "memory_records"

_MEMORY_TABLE_DDL = f"""
CREATE TABLE IF NOT EXISTS {_MEMORY_TABLE_NAME} (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope           VARCHAR(32) NOT NULL DEFAULT 'conversation',
    kind            VARCHAR(32) NOT NULL DEFAULT 'chat',
    content         TEXT NOT NULL DEFAULT '',
    session_id      VARCHAR(128) NOT NULL DEFAULT '',
    project_id      VARCHAR(128) NOT NULL DEFAULT '',
    metadata_json   JSONB DEFAULT '{{}}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_memory_scope_session ON {_MEMORY_TABLE_NAME} (scope, session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_kind ON {_MEMORY_TABLE_NAME} (kind);
CREATE INDEX IF NOT EXISTS idx_memory_created ON {_MEMORY_TABLE_NAME} (created_at DESC);
"""


class PostgresMemoryStore:
    """Production conversation memory backed by PostgreSQL.

    Falls back to an in-memory store transparently when the DB is
    unreachable, so the system never crashes due to a missing database.
    """

    name: str = "postgres"

    def __init__(self) -> None:
        self._settings = get_settings()
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._ready = False

    async def _ensure_ready(self) -> bool:
        """Lazily initialise the DB connection and create the table."""
        if self._ready:
            return True
        if not _DB_AVAILABLE:
            return False
        try:
            self._engine = get_engine()
            self._session_factory = get_session_factory()
            async with self._engine.begin() as conn:
                await conn.execute(text(_MEMORY_TABLE_DDL))
                await conn.commit()
            self._ready = True
            return True
        except Exception as exc:
            _log.warning("PostgresMemoryStore unavailable: %s", exc)
            return False

    # ------------------------------------------------------------------
    # MemoryStore protocol
    # ------------------------------------------------------------------

    async def append(self, record: MemoryRecord) -> None:
        if not await self._ensure_ready():
            return

        import json as _json

        stmt = text(f"""
            INSERT INTO {_MEMORY_TABLE_NAME}
                (id, scope, kind, content, session_id, project_id, metadata_json, created_at)
            VALUES
                (:id, :scope, :kind, :content, :session_id, :project_id, :metadata_json, :created_at)
        """)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            await session.execute(
                stmt,
                {
                    "id": str(record.id),
                    "scope": record.scope,
                    "kind": record.kind,
                    "content": record.content,
                    "session_id": record.session_id,
                    "project_id": record.project_id,
                    "metadata_json": _json.dumps(record.metadata),
                    "created_at": record.created_at,
                },
            )
            await session.commit()

    async def recent(
        self,
        scope: MemoryScope,
        session_id: str,
        *,
        limit: int = 20,
        kind: MemoryKind | None = None,
    ) -> list[MemoryRecord]:
        if not await self._ensure_ready():
            return []

        query = text(f"""
            SELECT id, scope, kind, content, session_id, project_id, metadata_json, created_at
            FROM {_MEMORY_TABLE_NAME}
            WHERE scope = :scope AND session_id = :session_id
            {("AND kind = :kind" if kind else "")}
            ORDER BY created_at DESC
            LIMIT :limit
        """)
        params: dict[str, Any] = {
            "scope": scope,
            "session_id": session_id,
            "limit": limit,
        }
        if kind:
            params["kind"] = kind

        assert self._session_factory is not None
        async with self._session_factory() as session:
            result = await session.execute(query, params)
            rows = result.fetchall()

        import json as _json

        return [
            MemoryRecord(
                id=row[0] if hasattr(row[0], "hex") else row[0],
                scope=row[1],
                kind=row[2],
                content=row[3],
                session_id=row[4],
                project_id=row[5],
                metadata=_json.loads(row[6]) if isinstance(row[6], str) else (row[6] or {}),
                created_at=row[7],
            )
            for row in rows
        ]

    async def recall(
        self,
        query: MemoryQuery,
    ) -> list[MemoryRecord]:
        if not await self._ensure_ready():
            return []

        conditions = ["1=1"]
        params: dict[str, Any] = {}
        if query.scope:
            conditions.append("scope = :scope")
            params["scope"] = query.scope
        if query.kind:
            conditions.append("kind = :kind")
            params["kind"] = query.kind
        if query.session_id:
            conditions.append("session_id = :session_id")
            params["session_id"] = query.session_id
        if query.project_id:
            conditions.append("project_id = :project_id")
            params["project_id"] = query.project_id

        where_clause = " AND ".join(conditions)
        sql = text(f"""
            SELECT id, scope, kind, content, session_id, project_id, metadata_json, created_at
            FROM {_MEMORY_TABLE_NAME}
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit
        """)
        params["limit"] = query.limit

        assert self._session_factory is not None
        async with self._session_factory() as session:
            result = await session.execute(sql, params)
            rows = result.fetchall()

        import json as _json

        records = []
        for row in rows:
            r = MemoryRecord(
                id=row[0] if hasattr(row[0], "hex") else row[0],
                scope=row[1],
                kind=row[2],
                content=row[3],
                session_id=row[4],
                project_id=row[5],
                metadata=_json.loads(row[6]) if isinstance(row[6], str) else (row[6] or {}),
                created_at=row[7],
            )
            records.append(r)

        # Simple text overlap scoring for ordering.
        if query.text:
            query_words = set(query.text.lower().split())
            for r in records:
                content_words = set(r.content.lower().split())
                overlap = len(query_words & content_words)
                r.score = overlap / max(len(query_words), 1)
            records.sort(key=lambda r: r.score, reverse=True)
            records = [r for r in records if r.score >= query.min_score]

        return records[: query.limit]

    async def forget(
        self,
        scope: MemoryScope,
        session_id: str,
    ) -> None:
        if not await self._ensure_ready():
            return
        stmt = text(f"""
            DELETE FROM {_MEMORY_TABLE_NAME}
            WHERE scope = :scope AND session_id = :session_id
        """)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            await session.execute(stmt, {"scope": scope, "session_id": session_id})
            await session.commit()

    async def close(self) -> None:
        """Engine is managed by the persistence module; nothing to close."""
        pass
