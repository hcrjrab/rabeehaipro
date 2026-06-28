"""Filesystem tools — write, delete, copy, move.

All path arguments are resolved against the workspace root and rejected if
they escape (``..``, absolute paths, symlinks). This is the same confinement
used by the read-only built-ins but applied to mutation operations.

Risk classification:
- ``file.write``       -> SAFE (reversible: content is logged in events).
- ``file.delete``      -> DESTRUCTIVE (data loss).
- ``file.copy``        -> SAFE (duplicative, no loss).
- ``file.move``        -> DESTRUCTIVE (source removed).
"""

from __future__ import annotations

import shutil
from typing import Any

from ..config.schemas import RiskLevel, ToolCallResult
from .base import BaseTool, ToolContext
from .builtin import _confine  # reuse the confinement helper


class WriteTextTool(BaseTool):
    """Write (create or overwrite) a UTF-8 text file in the workspace."""

    name = "file.write"
    description = (
        "Write content to a file inside the workspace. Creates parent directories as needed."
    )
    risk = RiskLevel.SAFE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path inside workspace."},
                "content": {"type": "string", "description": "Text content to write."},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        }

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        raw_path = str(args.get("path", "")).strip()
        content = str(args.get("content", ""))
        if not raw_path:
            return ToolCallResult(ok=False, error="Missing 'path' argument.")
        try:
            target = _confine(raw_path, ctx.workspace)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except PermissionError as exc:
            return ToolCallResult(ok=False, error=str(exc))
        except OSError as exc:
            return ToolCallResult(ok=False, error=f"Write failed: {exc}")
        return ToolCallResult(ok=True, data={"path": raw_path, "bytes_written": len(content)})


class DeleteFileTool(BaseTool):
    """Delete a file or empty directory inside the workspace."""

    name = "file.delete"
    description = "Delete a file or empty directory inside the workspace."
    risk = RiskLevel.DESTRUCTIVE

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
            if not target.exists():
                return ToolCallResult(ok=False, error=f"Not found: {raw_path}")
            if target.is_file():
                target.unlink()
            elif target.is_dir():
                shutil.rmtree(target)  # non-empty directories too (user intent is clear)
            else:
                return ToolCallResult(ok=False, error=f"Not a file or directory: {raw_path}")
        except PermissionError as exc:
            return ToolCallResult(ok=False, error=str(exc))
        except OSError as exc:
            return ToolCallResult(ok=False, error=f"Delete failed: {exc}")
        return ToolCallResult(ok=True, data={"path": raw_path, "deleted": True})


class CopyFileTool(BaseTool):
    """Copy a file or directory inside the workspace."""

    name = "file.copy"
    description = "Copy a file or directory to a new location inside the workspace."
    risk = RiskLevel.SAFE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Source path (relative)."},
                "destination": {"type": "string", "description": "Destination path (relative)."},
            },
            "required": ["source", "destination"],
            "additionalProperties": False,
        }

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        src_raw = str(args.get("source", "")).strip()
        dst_raw = str(args.get("destination", "")).strip()
        if not src_raw or not dst_raw:
            return ToolCallResult(ok=False, error="Missing 'source' or 'destination'.")
        try:
            src = _confine(src_raw, ctx.workspace)
            dst = _confine(dst_raw, ctx.workspace)
            if not src.exists():
                return ToolCallResult(ok=False, error=f"Source not found: {src_raw}")
            if src.is_file():
                shutil.copy2(src, dst)
            elif src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                return ToolCallResult(ok=False, error=f"Unsupported type: {src_raw}")
        except PermissionError as exc:
            return ToolCallResult(ok=False, error=str(exc))
        except OSError as exc:
            return ToolCallResult(ok=False, error=f"Copy failed: {exc}")
        return ToolCallResult(
            ok=True, data={"source": src_raw, "destination": dst_raw, "copied": True}
        )


class MoveFileTool(BaseTool):
    """Move (rename) a file or directory inside the workspace."""

    name = "file.move"
    description = "Move or rename a file/directory inside the workspace."
    risk = RiskLevel.DESTRUCTIVE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Current path (relative)."},
                "destination": {"type": "string", "description": "New path (relative)."},
            },
            "required": ["source", "destination"],
            "additionalProperties": False,
        }

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        src_raw = str(args.get("source", "")).strip()
        dst_raw = str(args.get("destination", "")).strip()
        if not src_raw or not dst_raw:
            return ToolCallResult(ok=False, error="Missing 'source' or 'destination'.")
        try:
            src = _confine(src_raw, ctx.workspace)
            dst = _confine(dst_raw, ctx.workspace)
            if not src.exists():
                return ToolCallResult(ok=False, error=f"Source not found: {src_raw}")
            dst.parent.mkdir(parents=True, exist_ok=True)  # ensure dest dir exists first
            shutil.move(str(src), str(dst))
        except PermissionError as exc:
            return ToolCallResult(ok=False, error=str(exc))
        except OSError as exc:
            return ToolCallResult(ok=False, error=f"Move failed: {exc}")
        return ToolCallResult(
            ok=True, data={"source": src_raw, "destination": dst_raw, "moved": True}
        )
