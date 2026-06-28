"""Abstract tool base + execution context.

Tools are intentionally synchronous-looking in their public surface but the
orchestrator always awaits them (they may be I/O bound). Pure-CPU tools can
just be ``async def`` that do their work inline; blocking tools should
delegate to ``asyncio.to_thread`` to stay non-blocking.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from ..config.schemas import RiskLevel, ToolCallResult

_log = logging.getLogger(__name__)


@dataclass(slots=True)
class ToolContext:
    """Per-call execution context handed to every tool.

    Carries identifiers needed for audit logging and a scratchpad the
    orchestrator can use to pass prior outputs between tools within a task.
    """

    task_id: UUID
    session_id: UUID
    workspace: str  # sandboxed root path for filesystem tools
    scratchpad: dict[str, Any] = field(default_factory=dict)


class BaseTool(ABC):
    """Contract every tool satisfies.

    Class attributes provide static metadata (used by the registry and the
    approval gate) without instantiating the tool.
    """

    name: str = "base"
    description: str = "Override me."
    risk: RiskLevel = RiskLevel.NONE

    @abstractmethod
    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        """Run the tool and return a structured result."""
        raise NotImplementedError

    def schema(self) -> dict[str, Any]:
        """JSON-schema fragment describing ``args`` for LLM function-calling.

        Default: empty object. Override to declare parameters.
        """
        return {"type": "object", "properties": {}}

    # Convenience: the OpenAI-style function descriptor used by providers.
    def as_function_tool(self) -> dict[str, Any]:
        """Return the tool in OpenAI ``tools`` format for the LLM."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.schema(),
            },
        }
