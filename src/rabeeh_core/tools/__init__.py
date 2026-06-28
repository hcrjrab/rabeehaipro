"""Tool bounded context.

A *tool* is a capability the agent can ask the orchestrator to run: read a
file, run a shell command (sandboxed), open a browser tab, generate an
invoice, etc. Tools are the ONLY path from an agent to the outside world.

Design
------
- :class:`BaseTool` defines the contract: ``name``, ``risk``, ``schema`` (for
  the LLM's function-calling) and an async ``execute``.
- :class:`ToolRegistry` resolves tool names to instances and exposes a JSON
  schema bundle for the LLM.
- The orchestrator holds the registry; agents only ever *name* a tool.
"""

from __future__ import annotations

from .base import BaseTool, ToolContext
from .builtin import EchoTool, ListDirTool, ReadTextTool
from .registry import ToolRegistry, get_registry

__all__ = [
    "BaseTool",
    "EchoTool",
    "ListDirTool",
    "ReadTextTool",
    "ToolContext",
    "ToolRegistry",
    "get_registry",
]
