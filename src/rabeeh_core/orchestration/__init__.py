"""Orchestration bounded context.

The orchestrator is the *conductor*: it owns the task lifecycle, drives
agents in sequence, routes their tool-call proposals through the approval
gate, executes approved tools via the registry, and records every step as
an immutable :class:`TaskEvent`.

Two runners share the same state and node logic:

- :class:`Orchestrator` — a linear planner -> executor -> reviewer loop,
  fully runnable with the mock LLM and built-in tools (no extra deps).
- :class:`GraphOrchestrator` — the same nodes wired as a LangGraph
  ``StateGraph`` with review-driven conditional edges (replan / retry /
  finish). Requires the ``langgraph`` extra.
"""

from __future__ import annotations

from typing import Any

from .runner import Orchestrator, OrchestratorState, get_orchestrator  # type: ignore[attr-defined]

__all__ = ["Orchestrator", "OrchestratorState", "get_orchestrator"]


def __getattr__(name: str) -> Any:  # pragma: no cover - lazy import shim
    """Lazy-load the graph orchestrator so langgraph stays an optional dep.

    Importing ``GraphOrchestrator`` eagerly would force langgraph to be
    installed even for users only wanting the linear runner; this PEP 562
    shim defers the import to first access.
    """
    if name in {"GraphOrchestrator", "get_graph_orchestrator"}:
        from .graph import GraphOrchestrator, get_graph_orchestrator

        return {
            "GraphOrchestrator": GraphOrchestrator,
            "get_graph_orchestrator": get_graph_orchestrator,
        }[name]
    raise AttributeError(f"module 'rabeeh_core.orchestration' has no attribute {name!r}")
