"""Code execution tool — run a Python script in a confined subprocess.

The agent writes code via ``file.write`` then runs it with ``code.run``. The
tool executes in a subprocess with:

- A strict timeout (default 30s, capped at 120s) to prevent infinite loops.
- The workspace as the CWD so relative paths resolve correctly.
- stdout + stderr captured and returned.

Risk: DESTRUCTIVE — arbitrary code can do anything (network, files). The
approval gate will pause before execution unless policy=none.

Note: this is the *constrained* sandbox. Phase 6 will add Docker-based
isolation for truly untrusted code; this tool is for the agent running the
user's own code on the user's own machine.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from typing import Any

from ..config.schemas import RiskLevel, ToolCallResult
from .base import BaseTool, ToolContext
from .builtin import _confine

_log = logging.getLogger(__name__)

_MAX_TIMEOUT = 120  # hard cap regardless of what the caller requests


class RunCodeTool(BaseTool):
    """Run a Python script from the workspace in a subprocess."""

    name = "code.run"
    description = (
        "Run a Python script located in the workspace. Captures stdout/stderr. "
        "Use file.write to create the script first."
    )
    risk = RiskLevel.DESTRUCTIVE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Script path (relative to workspace)."},
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default 30, max 120).",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Command-line arguments to pass to the script.",
                },
            },
            "required": ["path"],
        }

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        raw_path = str(args.get("path", "")).strip()
        if not raw_path:
            return ToolCallResult(ok=False, error="Missing 'path' argument.")

        try:
            target = _confine(raw_path, ctx.workspace)
            if not target.is_file():
                return ToolCallResult(ok=False, error=f"Script not found: {raw_path}")
        except PermissionError as exc:
            return ToolCallResult(ok=False, error=str(exc))

        timeout = min(int(args.get("timeout", 30)), _MAX_TIMEOUT)
        script_args = [str(a) for a in (args.get("args") or [])]

        # Build the command: current interpreter + script + args.
        cmd = [sys.executable, str(target), *script_args]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(ctx.workspace),
            )
        except OSError as exc:
            return ToolCallResult(ok=False, error=f"Failed to start process: {exc}")

        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            return ToolCallResult(
                ok=False,
                error=f"Script timed out after {timeout}s and was killed.",
            )

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        exit_code = proc.returncode or 0

        return ToolCallResult(
            ok=exit_code == 0,
            data={
                "path": raw_path,
                "exit_code": exit_code,
                "stdout": stdout[:20_000],  # cap output size
                "stderr": stderr[:20_000],
                "stdout_truncated": len(stdout) > 20_000,
            },
            error=None if exit_code == 0 else f"Process exited with code {exit_code}",
        )
