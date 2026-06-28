"""Task repository: async CRUD over the ORM with in-memory fallback.

The repository is the single place that translates between orchestrator
state (``OrchestratorState``) and durable rows (``TaskRow`` + events). The
API layer talks only to this repository, never to the ORM directly.

Fallback contract
-----------------
If :func:`db_available` is False, every method transparently uses an
in-process dict so the app remains fully functional in dev. Callers never
need to know which backend answered.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select

from ..orchestration.state import OrchestratorState
from .db import db_available, get_session_factory
from .models import TaskEventRow, TaskRow

_log = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TaskRepository:
    """Persist + retrieve tasks, with graceful in-memory degradation."""

    def __init__(self) -> None:
        # In-memory fallback store: task_id -> serialised snapshot dict.
        self._cache: dict[UUID, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    async def save(self, state: OrchestratorState) -> None:
        """Upsert an orchestrator state (task + full event timeline)."""
        snapshot = self._serialise(state)
        self._cache[state.id] = snapshot  # always keep the cache warm

        if not db_available():
            return

        session_factory = get_session_factory()
        try:
            async with session_factory() as session:
                # Upsert the task row.
                existing = await session.get(TaskRow, state.id)
                if existing is None:
                    row = self._state_to_row(state)
                    session.add(row)
                else:
                    self._update_row(existing, state)
                    # Clear existing events before re-adding.
                    await session.execute(
                        delete(TaskEventRow).where(TaskEventRow.task_id == state.id)
                    )
                # Always persist the full event timeline (insert + update paths).
                for event in state.events:
                    session.add(
                        TaskEventRow(
                            id=event.id,
                            task_id=state.id,
                            kind=event.kind,
                            payload=event.payload,
                            created_at=event.created_at,
                        )
                    )
                await session.commit()
        except Exception as exc:
            _log.warning("DB save failed; snapshot kept in memory only. (%s)", exc)

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------
    async def get(self, task_id: UUID) -> dict[str, Any] | None:
        """Return a task snapshot by id, or None if unknown."""
        if task_id in self._cache and db_available() is False:
            return self._cache[task_id]

        if not db_available():
            return self._cache.get(task_id)

        session_factory = get_session_factory()
        try:
            async with session_factory() as session:
                row = await session.get(TaskRow, task_id)
                if row is None:
                    return None
                return self._row_to_snapshot(row)
        except Exception as exc:
            _log.warning("DB get failed; serving from in-memory cache. (%s)", exc)
            return self._cache.get(task_id)

    async def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent task snapshots (newest first)."""
        if not db_available():
            return sorted(
                self._cache.values(),
                key=lambda s: s.get("created_at", ""),
                reverse=True,
            )[:limit]

        session_factory = get_session_factory()
        try:
            async with session_factory() as session:
                stmt = select(TaskRow).order_by(TaskRow.created_at.desc()).limit(limit)
                rows = (await session.execute(stmt)).scalars().all()
                return [self._row_to_snapshot(r) for r in rows]
        except Exception as exc:
            _log.warning("DB list failed; serving from in-memory cache. (%s)", exc)
            return list(self._cache.values())[:limit]

    # ------------------------------------------------------------------
    # (De)serialisation helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _serialise(state: OrchestratorState) -> dict[str, Any]:
        """Build the API-shaped snapshot from orchestrator state."""
        snap = state.snapshot()
        snap["events"] = [e.model_dump(mode="json") for e in state.events]
        if state.plan is not None:
            snap["plan"] = state.plan.model_dump(mode="json")
        snap["tool_results"] = [r.model_dump(mode="json") for r in state.tool_results]
        return snap

    @staticmethod
    def _state_to_row(state: OrchestratorState) -> TaskRow:
        plan = state.plan.model_dump(mode="json") if state.plan else None
        return TaskRow(
            id=state.id,
            session_id=state.session_id,
            goal=state.goal,
            status=state.status.value,
            error=state.error,
            plan=plan,
            tool_results=[r.model_dump(mode="json") for r in state.tool_results] or None,
            iterations=state.iterations,
            max_iterations=state.max_iterations,
            created_at=state.created_at,
            updated_at=state.updated_at,
        )

    @staticmethod
    def _update_row(row: TaskRow, state: OrchestratorState) -> None:
        row.status = state.status.value
        row.error = state.error
        row.plan = state.plan.model_dump(mode="json") if state.plan else None
        row.tool_results = [r.model_dump(mode="json") for r in state.tool_results] or None
        row.iterations = state.iterations
        row.updated_at = _utcnow()

    @staticmethod
    def _row_to_snapshot(row: TaskRow) -> dict[str, Any]:
        """Reconstruct the API snapshot from a hydrated ORM row."""
        return {
            "id": str(row.id),
            "session_id": str(row.session_id),
            "goal": row.goal,
            "status": row.status,
            "error": row.error,
            "plan": row.plan,
            "tool_results": row.tool_results or [],
            "iterations": row.iterations,
            "max_iterations": row.max_iterations,
            "events": [
                {
                    "id": str(e.id),
                    "task_id": str(e.task_id),
                    "kind": e.kind,
                    "payload": e.payload,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in row.events
            ],
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_repository: TaskRepository | None = None


def get_repository() -> TaskRepository:
    """Return the shared repository (lazy)."""
    global _repository
    if _repository is None:
        _repository = TaskRepository()
    return _repository


def reset_repository() -> None:
    """Reset the singleton + clear the in-memory cache (tests)."""
    global _repository
    _repository = None
