"""ChromaDB-backed vector memory store.

Provides semantic search across stored documents using embedding-based
retrieval. ChromaDB runs in-process (persistent client) by default, with
optional HTTP client mode for production deployments.

The store is used by the MemoryService for long-term semantic recall.
"""

from __future__ import annotations

import contextlib
import logging
import uuid as _uuid
from pathlib import Path
from typing import Any, cast

from .base import MemoryKind, MemoryRecord, MemoryScope

_log = logging.getLogger(__name__)

# Guard: chromadb is an optional extra.
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    CHROMA_ENABLED = True
except ImportError:  # pragma: no cover
    CHROMA_ENABLED = False
    _log.warning("chromadb not installed; vector memory unavailable.")
    chromadb = cast(Any, None)
    ChromaSettings = cast(Any, None)  # type: ignore[misc]


class ChromaMemoryStore:
    """Vector memory store backed by ChromaDB.

    Uses a persistent ``chromadb`` client by default. Collections are
    created per memory scope, so ``scope="long_term"`` maps to a
    ``long_term`` Chroma collection.

    Embeddings are computed on-the-fly by ChromaDB's built-in all-MiniLM-L6-v2
    model unless a custom embedding function is provided.
    """

    name: str = "chroma"

    def __init__(
        self,
        persist_directory: str | Path = ".data/chroma",
        collection_prefix: str = "rabeeh_",
        embedding_function: Any = None,
    ) -> None:
        if not CHROMA_ENABLED:
            raise RuntimeError(
                "ChromaDB is not installed. Install with: pip install 'rabeeh-core[vector]'"
            )

        self._persist_dir = Path(persist_directory)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._prefix = collection_prefix
        self._client = chromadb.PersistentClient(
            path=str(self._persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._embedding_fn = embedding_function
        self._collections: dict[str, Any] = {}

    def _collection(self, scope: MemoryScope = "long_term") -> Any:
        """Get or create a Chroma collection for the given scope."""
        name = f"{self._prefix}{scope}"
        if name not in self._collections:
            self._collections[name] = self._client.get_or_create_collection(
                name=name,
                embedding_function=self._embedding_fn,
            )
        return self._collections[name]

    # ------------------------------------------------------------------
    # VectorMemoryStore protocol
    # ------------------------------------------------------------------

    async def add_document(
        self,
        content: str,
        *,
        scope: MemoryScope = "long_term",
        kind: MemoryKind = "insight",
        metadata: dict[str, Any] | None = None,
        embedding: list[float] | None = None,
    ) -> str:
        doc_id = str(_uuid.uuid4())
        meta: dict[str, Any] = {
            "kind": kind,
            "scope": scope,
            **(metadata or {}),
        }

        def _add() -> None:
            self._collection(scope).add(
                documents=[content],
                metadatas=[meta],
                ids=[doc_id],
                embeddings=[embedding] if embedding else None,
            )

        await asyncio_get_loop(_add)
        _log.debug("Added document %s to Chroma scope=%s", doc_id, scope)
        return doc_id

    async def similarity_search(
        self,
        query: str,
        *,
        top_k: int = 10,
        scope: MemoryScope | None = None,
        score_threshold: float = 0.0,
    ) -> list[MemoryRecord]:
        def _search() -> list[tuple[str, float, str, dict[str, Any]]]:
            results = []
            scopes = [scope] if scope else ["conversation", "project", "long_term", "preference"]
            for s in scopes:
                try:
                    coll = self._collection(s)
                    query_results = coll.query(
                        query_texts=[query],
                        n_results=min(top_k, 100),
                    )
                    ids = query_results.get("ids", [[]])[0]
                    distances = query_results.get("distances", [[]])[0]
                    documents = query_results.get("documents", [[]])[0]
                    metadatas = query_results.get("metadatas", [[]])[0]

                    for i in range(len(ids)):
                        score = 1.0 - distances[i] if i < len(distances) else 0.5
                        if score >= score_threshold:
                            results.append(
                                (
                                    ids[i],
                                    score,
                                    documents[i] if i < len(documents) else "",
                                    metadatas[i] if i < len(metadatas) else {},
                                )
                            )
                except Exception:
                    _log.debug("Chroma query scope=%s failed", s, exc_info=True)
            return results

        raw = await asyncio_get_loop(_search)
        records = []
        for _doc_id, score, content, meta in raw:
            records.append(
                MemoryRecord(
                    content=content,
                    scope=meta.get("scope", "long_term"),
                    kind=meta.get("kind", "insight"),
                    metadata={k: v for k, v in meta.items() if k not in ("scope", "kind")},
                    score=score,
                )
            )
        records.sort(key=lambda r: r.score, reverse=True)
        return records[:top_k]

    async def delete_document(self, doc_id: str) -> None:
        for scope_name in ["conversation", "project", "long_term", "preference"]:

            def _delete(s: str = scope_name, d: str = doc_id) -> None:
                with contextlib.suppress(Exception):
                    self._collection(s).delete(ids=[d])

            await asyncio_get_loop(_delete)

    async def count(self) -> int:
        def _count_all() -> int:
            total = 0
            for scope_name in ["conversation", "project", "long_term", "preference"]:
                with contextlib.suppress(Exception):
                    total += self._collection(scope_name).count()
            return total

        return int(await asyncio_get_loop(_count_all))

    async def close(self) -> None:
        """ChromaDB persistent client doesn't require explicit close."""
        pass


# ---------------------------------------------------------------------------
# Helper: run sync code in a thread to avoid blocking the event loop
# ---------------------------------------------------------------------------


async def asyncio_get_loop(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a synchronous function in the default executor."""
    import asyncio

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
