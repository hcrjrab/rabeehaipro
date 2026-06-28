"""Task endpoints.

- ``POST /tasks``          -> submit a goal (Celery async or sync fallback).
- ``GET  /tasks``          -> list recent tasks (newest first).
- ``GET  /tasks/{id}``     -> fetch a previously-created task (durable).
- ``GET  /tasks/{id}/status`` -> lightweight status poll for Celery tasks.

When Celery + Redis is available the POST returns immediately with
``{"task_id": …, "status": "queued"}``.  Otherwise it falls back to
synchronous in-process execution exactly as Phase 1 did.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from ...config.schemas import TaskCreate
from ...orchestration.runner import get_orchestrator
from ...persistence.repository import get_repository

_log = logging.getLogger(__name__)

router = APIRouter()


@router.post("")
async def create_task(payload: TaskCreate) -> dict[str, object]:
    """Submit a goal for execution.

    Returns immediately with a ``task_id`` when Celery is available, or runs
    synchronously and returns the full snapshot on fallback.
    """
    try:
        from ..tasks.orchestrator_tasks import run_goal as run_goal_task
    except ImportError:
        run_goal_task = None

    if run_goal_task is not None:
        try:
            task = run_goal_task.delay(
                payload.goal,
                str(payload.session_id) if payload.session_id else None,
            )
            return {"task_id": task.id, "status": "queued"}
        except Exception as exc:
            _log.warning("Celery submit failed, falling back to sync: %s", exc)

    orch = get_orchestrator()
    state = await orch.run(payload.goal, session_id=payload.session_id)
    repo = get_repository()
    await repo.save(state)
    snapshot = await repo.get(state.id)
    return snapshot or state.snapshot()


@router.get("")
async def list_tasks(limit: int = Query(50, ge=1, le=200)) -> dict[str, object]:
    """List recent tasks (newest first)."""
    repo = get_repository()
    tasks = await repo.list_recent(limit=limit)
    return {"tasks": tasks, "count": len(tasks)}


@router.get("/{task_id}")
async def get_task(task_id: UUID) -> dict[str, object]:
    """Fetch a previously-created task (from Postgres or the in-memory cache)."""
    repo = get_repository()
    snapshot = await repo.get(task_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")
    return snapshot


@router.get("/{task_id}/status")
async def get_task_status(task_id: UUID) -> dict[str, object]:
    """Lightweight status poll for Celery-submitted tasks.

    Returns the full snapshot when the task is known to the repository,
    or a minimal ``{"status": "pending"}`` if it hasn't been persisted yet.
    """
    repo = get_repository()
    snapshot = await repo.get(task_id)
    if snapshot is None:
        return {"task_id": str(task_id), "status": "pending"}
    return {
        "task_id": str(snapshot.get("id", task_id)),
        "status": snapshot.get("status", "unknown"),
        "error": snapshot.get("error"),
        "updated_at": snapshot.get("updated_at"),
    }
