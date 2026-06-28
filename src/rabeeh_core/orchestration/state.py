"""Orchestrator state object.

This is the single mutable object threaded through every orchestration step.
Keeping it explicit (rather than a loose dict) gives:

- Static typing for every node.
- A clean serialization target for persistence (Phase 2 Postgres).
- A natural place to hang counters/limits used by the guardrails.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from ..config.schemas import (
    AgentMessage,
    TaskEvent,
    TaskPlan,
    TaskStatus,
    ToolCallResult,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class OrchestratorState:
    """Mutable state for one task run.

    Fields are grouped: identity -> lifecycle -> plan -> logs -> counters.
    """

    # Identity
    id: UUID = field(default_factory=uuid4)
    session_id: UUID = field(default_factory=uuid4)
    goal: str = ""

    # Lifecycle
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    error: str | None = None

    # Plan + conversation + tool results
    plan: TaskPlan | None = None
    history: list[AgentMessage] = field(default_factory=list)
    tool_results: list[ToolCallResult] = field(default_factory=list)
    events: list[TaskEvent] = field(default_factory=list)

    # Counters / guardrails
    iterations: int = 0
    max_iterations: int = 20

    # Arbitrary scratchpad for agents/tools (e.g. staged file paths).
    scratchpad: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Mutators (centralise side effects so nodes stay pure)
    # ------------------------------------------------------------------
    def touch(self) -> None:
        """Bump ``updated_at`` on any mutation."""
        self.updated_at = _utcnow()

    def add_event(self, kind: str, payload: dict[str, Any]) -> TaskEvent:
        """Append an audit event and return it."""
        event = TaskEvent(task_id=self.id, kind=kind, payload=payload)
        self.events.append(event)
        self.touch()
        return event

    def append_message(self, message: AgentMessage) -> None:
        self.history.append(message)
        self.touch()

    def is_over_budget(self) -> bool:
        """True when the iteration guardrail has been tripped."""
        return self.iterations >= self.max_iterations

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-serialisable view (for API responses / logs)."""
        return {
            "id": str(self.id),
            "session_id": str(self.session_id),
            "goal": self.goal,
            "status": self.status.value,
            "iterations": self.iterations,
            "max_iterations": self.max_iterations,
            "events": len(self.events),
            "plan_steps": len(self.plan.steps) if self.plan else 0,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
