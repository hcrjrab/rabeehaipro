"""Celery async tasks that wrap the orchestrator.

Each task runs its own event loop via ``asyncio.run()`` because Celery
workers are synchronous by default.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from celery import shared_task

from ..orchestration.runner import get_orchestrator
from ..persistence.repository import get_repository

_log = logging.getLogger(__name__)


@shared_task(bind=True, acks_late=True, max_retries=3, default_retry_delay=5)  # type: ignore[untyped-decorator]
def run_goal(self: Any, goal: str, session_id: str | None = None) -> dict[str, Any]:
    """Execute a goal through the orchestrator and persist the result.

    Spawns a fresh event loop for the async orchestrator run, then stores
    the final state in the repository (Postgres or in-memory fallback).
    """
    try:
        sid = UUID(session_id) if session_id else None
        orch = get_orchestrator()
        state = asyncio.run(orch.run(goal, session_id=sid))
        repo = get_repository()
        asyncio.run(repo.save(state))
        snap = state.snapshot()
        reposnap = asyncio.run(repo.get(state.id))
        return reposnap or snap
    except Exception as exc:
        _log.exception("run_goal failed (goal=%r)", goal)
        raise self.retry(exc=exc) from exc
