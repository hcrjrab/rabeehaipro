"""In-process memory store.

A simple, thread-safe (via a single ``threading.Lock``) implementation. It
is the default so the app is fully functional offline. ``recall`` uses a
case-insensitive substring + word-overlap score, which is enough to exercise
the orchestrator; Phase 5 upgrades it to ChromaDB embeddings.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Iterator

from .base import MemoryKind, MemoryQuery, MemoryRecord, MemoryScope


def _tokenize(text: str) -> set[str]:
    """Lowercase alphanumeric tokeniser shared by scoring."""
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 1}


class InMemoryStore:
    """List-backed store implementing :class:`MemoryStore`."""

    def __init__(self) -> None:
        self._records: list[MemoryRecord] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # MemoryStore protocol
    # ------------------------------------------------------------------

    async def append(self, record: MemoryRecord) -> None:
        with self._lock:
            self._records.append(record)

    async def recent(
        self,
        scope: MemoryScope,
        session_id: str,
        *,
        limit: int = 20,
        kind: MemoryKind | None = None,
    ) -> list[MemoryRecord]:
        with self._lock:
            matched = [
                r
                for r in self._records
                if r.scope == scope
                and r.session_id == session_id
                and (kind is None or r.kind == kind)
            ]
        matched.sort(key=lambda r: r.created_at, reverse=True)
        return list(reversed(matched[-limit:]))

    async def recall(
        self,
        query: MemoryQuery,
    ) -> list[MemoryRecord]:
        """Token-overlap ranking. Returns best matches, most-recent tie-break."""
        query_tokens = _tokenize(query.text) if query.text else set()
        if not query_tokens:
            return await self.recent(
                query.scope or "conversation",
                query.session_id or "",
                limit=query.limit,
                kind=query.kind,
            )

        def score(r: MemoryRecord) -> tuple[int, float]:
            tokens = _tokenize(r.content)
            overlap = len(query_tokens & tokens)
            return overlap, r.created_at.timestamp()

        with self._lock:
            candidates = [
                r
                for r in self._records
                if (query.scope is None or r.scope == query.scope)
                and (query.kind is None or r.kind == query.kind)
                and (query.session_id is None or r.session_id == query.session_id)
            ]
        scored = sorted(candidates, key=score, reverse=True)
        return [
            r
            for r in scored
            if score(r)[0] > 0 and score(r)[0] / max(len(query_tokens), 1) >= query.min_score
        ][: query.limit]

    async def forget(
        self,
        scope: MemoryScope,
        session_id: str,
    ) -> None:
        with self._lock:
            self._records = [
                r for r in self._records if not (r.scope == scope and r.session_id == session_id)
            ]

    def __iter__(self) -> Iterator[MemoryRecord]:
        with self._lock:
            return iter(list(self._records))
