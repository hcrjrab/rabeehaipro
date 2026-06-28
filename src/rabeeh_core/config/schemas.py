"""Shared Pydantic schemas and enums.

These are *transport* and *domain-contract* models kept deliberately free of
persistence concerns (no ORM, no DB imports) so they can be reused across
the API layer, agents, tools, and the future Electron/Next frontend.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    """Timezone-aware UTC 'now' (avoids deprecated ``datetime.utcnow``)."""
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------
class TaskStatus(StrEnum):
    """Lifecycle states for an agent task / orchestrator run."""

    PENDING = "pending"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RiskLevel(StrEnum):
    """Risk classification used by the approval gate.

    ``none``     -> read-only / information only.
    ``safe``     -> reversible side effects (create file, write cache).
    ``destructive`` -> overwrite, delete, network mutation, money move.
    ``elevated``    -> credential use, mass bulk action, system change.
    """

    NONE = "none"
    SAFE = "safe"
    DESTRUCTIVE = "destructive"
    ELEVATED = "elevated"


class AgentRole(StrEnum):
    """Canonical set of agent roles. New agents MUST register here."""

    PLANNER = "planner"
    CODING = "coding"
    RESEARCH = "research"
    VISION = "vision"
    BROWSER = "browser"
    AUTOMATION = "automation"
    BUSINESS = "business"
    OFFICE = "office"
    FILE = "file"
    MEMORY = "memory"
    REVIEWER = "reviewer"


# ---------------------------------------------------------------------------
# Tool / Agent I/O contracts
# ---------------------------------------------------------------------------
class ToolCallRequest(BaseModel):
    """A request from an agent to invoke a tool.

    Carries enough metadata for the approval gate and audit log to make a
    decision without executing the tool.
    """

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""  # short justification, surfaced to the user for risky calls
    risk: RiskLevel = RiskLevel.NONE


class ToolCallResult(BaseModel):
    """Structured outcome of a tool invocation."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    data: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    requires_approval: bool = False


class AgentMessage(BaseModel):
    """A message exchanged between agents / stored in conversation memory.

    Mirrors the LangChain ``BaseMessage`` roles so we can convert losslessly.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    name: str | None = None  # agent/tool name
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Orchestrator / task contracts
# ---------------------------------------------------------------------------
class TaskCreate(BaseModel):
    """Inbound request to start an autonomous task."""

    model_config = ConfigDict(extra="forbid")

    goal: str = Field(..., min_length=1, max_length=4000)
    session_id: UUID | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    auto_approve_safe: bool = True  # if False, even SAFE actions pause for approval


class TaskStep(BaseModel):
    """One step produced by the Planner agent."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    description: str
    assigned_agent: AgentRole
    tool_hints: list[str] = Field(default_factory=list)
    expected_risk: RiskLevel = RiskLevel.NONE
    done: bool = False


class TaskPlan(BaseModel):
    """A decomposed plan: ordered steps toward the goal."""

    model_config = ConfigDict(extra="forbid")

    goal: str
    steps: list[TaskStep]
    notes: str = ""


class TaskEvent(BaseModel):
    """An immutable event in a task's execution timeline (audit-friendly)."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    kind: str  # "plan" | "tool_call" | "approval_requested" | "log" | "error" | ...
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)


class TaskSummary(BaseModel):
    """Public-facing task representation returned by the API."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    session_id: UUID
    goal: str
    status: TaskStatus
    plan: TaskPlan | None = None
    events: list[TaskEvent] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
