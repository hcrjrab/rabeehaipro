"""Built-in safe tools available out of the box.

These three are deliberately *read-only / non-destructive* so the default
registry can be handed to agents without any approval friction in dev:

- :class:`EchoTool`     -> plumbing/health tool, useful in tests.
- :class:`ReadTextTool` -> read a text file (path-confined to workspace).
- :class:`ListDirTool`  -> list a directory (path-confined to workspace).

Path confinement: filesystem tools resolve every path against the workspace
root and reject escapes (``..`` / absolute / symlink tricks). This is the
first line of defence; the approval gate and OS permissions are backups.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..config.schemas import RiskLevel, ToolCallResult
from .base import BaseTool, ToolContext


class EchoTool(BaseTool):
    """Trivial tool that echoes its input. Useful for smoke tests."""

    name = "echo"
    description = "Echo back the provided message. Useful for connectivity checks."
    risk = RiskLevel.NONE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
            "additionalProperties": False,
        }

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        message = str(args.get("message", ""))
        return ToolCallResult(ok=True, data={"echo": message})


# ---------------------------------------------------------------------------
# Filesystem confinement helper
# ---------------------------------------------------------------------------
def _confine(raw_path: str, workspace: str) -> Path:
    """Resolve ``raw_path`` strictly inside ``workspace``.

    Resolves symlinks and rejects any path that escapes the workspace. We
    use ``os.path.commonpath`` after normalisation to detect traversal.
    """
    ws = Path(workspace).resolve()
    candidate = (
        (ws / raw_path).resolve() if not os.path.isabs(raw_path) else Path(raw_path).resolve()
    )

    try:
        candidate.relative_to(ws)
    except ValueError as exc:
        raise PermissionError(f"Path '{raw_path}' escapes workspace '{ws}'.") from exc
    return candidate


class ReadTextTool(BaseTool):
    """Read a UTF-8 text file from within the workspace."""

    name = "file.read"
    description = "Read a UTF-8 text file located inside the agent workspace."
    risk = RiskLevel.NONE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path inside workspace."}
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        raw_path = str(args.get("path", "")).strip()
        if not raw_path:
            return ToolCallResult(ok=False, error="Missing 'path' argument.")
        try:
            target = _confine(raw_path, ctx.workspace)
            if not target.is_file():
                return ToolCallResult(ok=False, error=f"Not a file: {raw_path}")
            text = target.read_text(encoding="utf-8", errors="replace")
        except PermissionError as exc:
            return ToolCallResult(ok=False, error=str(exc))
        except OSError as exc:
            return ToolCallResult(ok=False, error=f"Read failed: {exc}")
        return ToolCallResult(ok=True, data={"path": raw_path, "content": text, "bytes": len(text)})


class ListDirTool(BaseTool):
    """List entries of a directory inside the workspace."""

    name = "file.list"
    description = "List the entries of a directory inside the agent workspace."
    risk = RiskLevel.NONE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory relative to workspace; '' = root.",
                }
            },
            "required": [],
            "additionalProperties": False,
        }

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        raw_path = str(args.get("path", "")).strip()
        try:
            target = _confine(raw_path or ".", ctx.workspace)
            if not target.is_dir():
                return ToolCallResult(ok=False, error=f"Not a directory: {raw_path or '.'}")
            entries = sorted(
                (
                    {
                        "name": p.name,
                        "type": "dir" if p.is_dir() else "file",
                        "size": p.stat().st_size if p.is_file() else 0,
                    }
                    for p in target.iterdir()
                ),
                key=lambda e: e["name"],
            )
        except PermissionError as exc:
            return ToolCallResult(ok=False, error=str(exc))
        except OSError as exc:
            return ToolCallResult(ok=False, error=f"List failed: {exc}")
        return ToolCallResult(ok=True, data={"path": raw_path or ".", "entries": entries})
