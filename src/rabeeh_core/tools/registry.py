"""Tool registry: name -> BaseTool instance, process-wide.

Holds the canonical set of tools available to the orchestrator. Agents do
not own tools; they *name* them. This indirection:

- Lets the approval gate classify risk from a single source of truth.
- Makes it trivial to enable/disable a capability per environment.
- Gives one place to enumerate the function-calling schema bundle sent to
  the LLM (``tools`` field in chat requests).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from .base import BaseTool

_log = logging.getLogger(__name__)


class ToolRegistry:
    """Mutable map of tool name -> instance."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> BaseTool:
        """Add (or replace) a tool. Returns the tool for chaining/tests."""
        if tool.name in self._tools:
            _log.warning("Overwriting already-registered tool %r", tool.name)
        self._tools[tool.name] = tool
        _log.debug("Registered tool %s (risk=%s)", tool.name, tool.risk)
        return tool

    def get(self, name: str) -> BaseTool | None:
        """Look up a tool by name, or ``None`` if unknown."""
        return self._tools.get(name)

    def require(self, name: str) -> BaseTool:
        """Look up or raise — use when the caller is sure the tool exists."""
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"Tool not registered: {name!r}")
        return tool

    def names(self) -> list[str]:
        """Sorted list of registered tool names (stable for diffs/tests)."""
        return sorted(self._tools)

    def all(self) -> Iterable[BaseTool]:
        """Iterate registered tools."""
        return self._tools.values()

    def function_schemas(self) -> list[dict[str, object]]:
        """OpenAI-style ``tools`` payload for every registered tool."""
        return [t.as_function_tool() for t in self._tools.values()]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._tools


# ---------------------------------------------------------------------------
# Process-wide singleton + default population
# ---------------------------------------------------------------------------
_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    """Return the shared registry, populating defaults on first access.

    Imports are lazy so optional tool packages (office, pdf, vision, computer)
    don't need to be installed for the base registry. Tools that depend on
    missing packages are silently skipped with a debug log.
    """
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        # Always-available read-only built-ins.
        from .builtin import EchoTool, ListDirTool, ReadTextTool

        for tool_cls in (EchoTool, ReadTextTool, ListDirTool):
            _registry.register(tool_cls())

        # File mutation tools (always available; workspace-confined).
        from .file import CopyFileTool, DeleteFileTool, MoveFileTool, WriteTextTool

        for tool_cls in (WriteTextTool, DeleteFileTool, CopyFileTool, MoveFileTool):  # type: ignore[assignment]
            _registry.register(tool_cls())

        # Code execution tool (always available; subprocess-based).
        from .code import RunCodeTool

        _registry.register(RunCodeTool())

        # Optional tool packs — try to import and skip on ImportError.
        _try_register(
            "office",
            ".office",
            [
                "CreateWordTool",
                "CreateExcelTool",
                "CreatePowerPointTool",
            ],
        )
        _try_register(
            "pdf",
            ".pdf_",
            [
                "CreatePdfTool",
                "ReadPdfTool",
            ],
        )
        _try_register(
            "vision",
            ".vision",
            [
                "ScreenshotTool",
                "OcrTool",
                "ScreenReadTool",
            ],
        )
        _try_register(
            "computer",
            ".computer",
            [
                "MouseClickTool",
                "MouseMoveTool",
                "MouseScrollTool",
                "MouseDragTool",
                "KeyboardTypeTool",
                "ClipboardTool",
                "ScreenLocateTool",
                "WindowListTool",
                "WindowFocusTool",
                "WindowCloseTool",
                "WindowResizeTool",
            ],
        )
        _try_register(
            "browser",
            ".browser",
            [
                "WebSearchTool",
                "WebFetchTool",
                "WebExtractTool",
                "WebClickTool",
                "WebFillFormTool",
                "WebScreenshotTool",
            ],
        )

        _log.info("Tool registry populated with %d tools", len(_registry))
    return _registry


def _try_register(pack_name: str, module_path: str, class_names: list[str]) -> None:
    """Import a tool module and register the named classes; skip on ImportError."""
    full_mod = f"rabeeh_core.tools{module_path}"
    try:
        mod = __import__(full_mod, fromlist=class_names)
    except ImportError:
        _log.debug("Tool pack '%s' not installed; skipping.", pack_name)
        return
    for name in class_names:
        tool_cls = getattr(mod, name, None)
        if tool_cls is not None and _registry is not None:
            _registry.register(tool_cls())


def reset_registry() -> None:
    """Clear the cached registry (tests / hot-reload)."""
    global _registry
    _registry = None
