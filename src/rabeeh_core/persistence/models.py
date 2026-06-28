"""SQLAlchemy ORM models for tasks + audit events.

Mirrors the domain schemas in :mod:`rabeeh_core.config.schemas` but kept
deliberately separate (no shared classes) so the persistence layer can evolve
its own table layout (indices, partitions) without coupling to the API DTOs.

Relationships
-------------
- ``TaskRow`` 1:N ``TaskEventRow`` (cascade delete): dropping a task removes
  its whole audit timeline, which is the correct behaviour for "forget me".
- JSON columns store the plan + tool results so we don't need dozens of
  child tables for what is effectively semi-structured data.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""


# JSON column type that works on both Postgres and SQLite (dev fallback).
_JSONType = JSON().with_variant(SQLITE_JSON, "sqlite")


class GUID(TypeDecorator[UUID]):
    """Platform-independent UUID column.

    Uses Postgres' native ``UUID`` type when available (fast, indexed), and
    falls back to a 36-char ``String`` on SQLite (dev). Crucially, the
    ``process_bind_param`` / ``process_result_value`` hooks convert between
    Python ``UUID`` objects and string bind parameters, which is required for
    the SQLite driver (it cannot bind ``UUID`` objects directly).

    Pattern from the SQLAlchemy "coercing typed dictionaries" cookbook.
    """

    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[no-untyped-def]
        """Pick the native UUID type on Postgres, String(36) elsewhere."""
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):  # type: ignore[no-untyped-def]
        """UUID -> str for non-Postgres dialects; pass through on Postgres."""
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value  # native UUID binding
        return str(value)

    def process_result_value(self, value, dialect):  # type: ignore[no-untyped-def]
        """str/UUID -> UUID object on read."""
        if value is None:
            return None
        if isinstance(value, UUID):
            return value
        return UUID(str(value))


class TaskRow(Base):
    """A single autonomous task / orchestrator run."""

    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(GUID(), nullable=False, index=True)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Semi-structured payload: the plan (steps) + final tool results.
    plan: Mapped[dict[str, Any] | None] = mapped_column(_JSONType, nullable=True)
    tool_results: Mapped[list[dict[str, Any]] | None] = mapped_column(_JSONType, nullable=True)

    iterations: Mapped[int] = mapped_column(default=0, nullable=False)
    max_iterations: Mapped[int] = mapped_column(default=20, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    events: Mapped[list[TaskEventRow]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskEventRow.created_at",
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<TaskRow {self.id} status={self.status}>"


class TaskEventRow(Base):
    """One immutable audit event in a task's timeline."""

    __tablename__ = "task_events"
    __table_args__ = (Index("ix_task_events_task_kind", "task_id", "kind"),)

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(_JSONType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    task: Mapped[TaskRow] = relationship(back_populates="events")

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<TaskEventRow {self.kind} task={self.task_id}>"
