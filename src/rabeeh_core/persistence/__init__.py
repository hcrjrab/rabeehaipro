"""Persistence bounded context (Phase 2).

Durable storage of tasks and their audit event timelines.

Strategy
--------
- Primary backend: an async SQLAlchemy 2.0 engine over Postgres (or SQLite
  for local dev via a ``sqlite+aiosqlite`` URL).
- Graceful degradation: if the DB is unreachable at boot, the repository
  falls back to the in-process dict cache so the app keeps working in dev.
- Migrations: Alembic (``alembic/``), so schema changes are versioned.

Public surface is the :class:`TaskRepository` plus :func:`get_repository`.
"""

from __future__ import annotations

from .db import db_available, get_engine, init_db
from .models import TaskEventRow, TaskRow
from .repository import TaskRepository, get_repository

__all__ = [
    "TaskEventRow",
    "TaskRepository",
    "TaskRow",
    "db_available",
    "get_engine",
    "get_repository",
    "init_db",
]
