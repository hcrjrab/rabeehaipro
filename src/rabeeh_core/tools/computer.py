"""Computer-use tools — mouse, keyboard, clipboard, screen locate, window mgmt.

These tools give the agent direct control of the desktop. Because they
perform real side effects on the user's machine, they are all classified as
at least ``SAFE`` (reversible) and many as ``DESTRUCTIVE`` or ``ELEVATED``.

Safety
------
- The approval gate will pause on destructive/elevated operations.
- ``pyautogui`` has a built-in fail-safe (move mouse to corner to abort).
- ``clipboard.copy`` is classified ``SAFE`` since it doesn't destroy data.

Dependencies (pyautogui, pyperclip, pillow) are imported lazily.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config.schemas import RiskLevel, ToolCallResult
from .base import BaseTool, ToolContext

_log = logging.getLogger(__name__)


class _ComputerTool(BaseTool):
    """Shared base: lazy import pyautogui with graceful ImportError."""

    risk = RiskLevel.SAFE

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        try:
            return await self._execute_checked(args, ctx)
        except ImportError as exc:
            return ToolCallResult(
                ok=False,
                error=f"Missing dependency: {exc}. Install computer-use deps: pip install pyautogui pyperclip pillow",
            )
        except Exception as exc:
            return ToolCallResult(ok=False, error=f"Computer-use error: {exc}")

    async def _execute_checked(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        raise NotImplementedError


class MouseClickTool(_ComputerTool):
    """Click the mouse at a position or the current position."""

    name = "mouse.click"
    description = (
        "Click the mouse at specified coordinates (x, y). Supports left/right/middle button."
    )
    risk = RiskLevel.SAFE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate."},
                "y": {"type": "integer", "description": "Y coordinate."},
                "button": {
                    "type": "string",
                    "enum": ["left", "right", "middle"],
                    "default": "left",
                },
                "clicks": {"type": "integer", "default": 1, "description": "Number of clicks."},
            },
            "required": ["x", "y"],
        }

    async def _execute_checked(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        import pyautogui

        pyautogui.PAUSE = 0.1  # small delay between actions for stability
        x = int(args["x"])
        y = int(args["y"])
        button = str(args.get("button", "left"))
        clicks = int(args.get("clicks", 1))
        pyautogui.click(x=x, y=y, button=button, clicks=clicks)
        return ToolCallResult(ok=True, data={"x": x, "y": y, "button": button, "clicks": clicks})


class MouseMoveTool(_ComputerTool):
    """Move the mouse to a position."""

    name = "mouse.move"
    description = "Move the mouse cursor to specified coordinates."
    risk = RiskLevel.SAFE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate."},
                "y": {"type": "integer", "description": "Y coordinate."},
                "duration": {
                    "type": "number",
                    "description": "Movement duration in seconds (smooth move).",
                },
            },
            "required": ["x", "y"],
        }

    async def _execute_checked(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        import pyautogui

        pyautogui.PAUSE = 0.1
        x = int(args["x"])
        y = int(args["y"])
        duration = float(args.get("duration", 0.25))
        pyautogui.moveTo(x, y, duration=duration)
        return ToolCallResult(ok=True, data={"x": x, "y": y, "duration": duration})


class KeyboardTypeTool(_ComputerTool):
    """Type text or press a key combination."""

    name = "keyboard.type"
    description = "Type text or press keyboard shortcuts (e.g. 'ctrl+c')."
    risk = RiskLevel.DESTRUCTIVE  # can trigger actions (delete, close, etc.)

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to type (use for literal text)."},
                "keys": {
                    "type": "string",
                    "description": "Key combo to press (e.g. 'ctrl+a', 'enter', 'tab').",
                },
                "interval": {
                    "type": "number",
                    "description": "Delay between keystrokes in seconds.",
                },
            },
        }

    async def _execute_checked(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        import pyautogui

        pyautogui.PAUSE = 0.1
        interval = float(args.get("interval", 0.02))

        text = str(args.get("text", ""))
        keys = str(args.get("keys", ""))

        if keys:
            pyautogui.hotkey(*keys.split("+")) if "+" in keys else pyautogui.press(keys)
            return ToolCallResult(ok=True, data={"keys": keys})
        if text:
            pyautogui.typewrite(text, interval=interval)
            return ToolCallResult(ok=True, data={"text": text, "chars": len(text)})

        return ToolCallResult(ok=False, error="Provide either 'text' or 'keys'.")


class ClipboardTool(_ComputerTool):
    """Read or write the system clipboard."""

    name = "clipboard"
    description = "Read from or write to the system clipboard."
    risk = RiskLevel.SAFE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["read", "write"]},
                "text": {
                    "type": "string",
                    "description": "Text to write (required when action=write).",
                },
            },
            "required": ["action"],
        }

    async def _execute_checked(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        import pyperclip

        action = str(args["action"])
        if action == "read":
            text = pyperclip.paste()
            return ToolCallResult(ok=True, data={"text": text, "chars": len(text)})
        elif action == "write":
            text = str(args.get("text", ""))
            pyperclip.copy(text)
            return ToolCallResult(ok=True, data={"action": "write", "chars": len(text)})
        return ToolCallResult(ok=False, error=f"Unknown action: {action}")


class WindowListTool(_ComputerTool):
    """List all visible windows."""

    name = "window.list"
    description = "List all visible windows with their titles and positions."
    risk = RiskLevel.NONE

    def schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def _execute_checked(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        import pyautogui

        # pyautogui doesn't directly enumerate windows; use the Windows API
        # via ctypes on Windows platforms.
        try:
            import ctypes
            from ctypes import wintypes

            EnumWindows = ctypes.windll.user32.EnumWindows  # type: ignore[attr-defined]
            GetWindowTextW = ctypes.windll.user32.GetWindowTextW  # type: ignore[attr-defined]
            IsWindowVisible = ctypes.windll.user32.IsWindowVisible  # type: ignore[attr-defined]
            GetWindowRect = ctypes.windll.user32.GetWindowRect  # type: ignore[attr-defined]

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)  # type: ignore[attr-defined]
            windows: list[dict[str, Any]] = []

            def _callback(hwnd: int, _lparam: int) -> bool:
                if IsWindowVisible(hwnd):
                    length = GetWindowTextW(hwnd, None, 0)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        GetWindowTextW(hwnd, buf, length + 1)
                        title = buf.value
                        rect = wintypes.RECT()
                        GetWindowRect(hwnd, ctypes.byref(rect))
                        windows.append(
                            {
                                "hwnd": hwnd,
                                "title": title,
                                "left": rect.left,
                                "top": rect.top,
                                "width": rect.right - rect.left,
                                "height": rect.bottom - rect.top,
                            }
                        )
                return True

            EnumWindows(WNDENUMPROC(_callback), 0)
            return ToolCallResult(ok=True, data={"windows": windows, "count": len(windows)})
        except (ImportError, AttributeError):
            # Fallback for non-Windows or restricted environments.
            size = pyautogui.size()
            return ToolCallResult(
                ok=True,
                data={"windows": [], "screen": {"width": size[0], "height": size[1]}},
            )


class MouseScrollTool(_ComputerTool):
    """Scroll the mouse wheel."""

    name = "mouse.scroll"
    description = "Scroll the mouse wheel. Positive = scroll up, negative = scroll down."
    risk = RiskLevel.SAFE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "clicks": {
                    "type": "integer",
                    "description": "Number of scroll steps (positive=up, negative=down).",
                    "default": 3,
                },
                "x": {"type": "integer", "description": "X coordinate to scroll at (optional)."},
                "y": {"type": "integer", "description": "Y coordinate to scroll at (optional)."},
            },
        }

    async def _execute_checked(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        import pyautogui

        pyautogui.PAUSE = 0.05
        clicks = int(args.get("clicks", 3))
        x = args.get("x")
        y = args.get("y")
        if x is not None and y is not None:
            pyautogui.scroll(clicks, x=int(x), y=int(y))
        else:
            pyautogui.scroll(clicks)
        return ToolCallResult(ok=True, data={"clicks": clicks})


class MouseDragTool(_ComputerTool):
    """Drag the mouse from one position to another."""

    name = "mouse.drag"
    description = "Click and drag the mouse from (start_x, start_y) to (end_x, end_y)."
    risk = RiskLevel.SAFE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "start_x": {"type": "integer", "description": "Starting X coordinate."},
                "start_y": {"type": "integer", "description": "Starting Y coordinate."},
                "end_x": {"type": "integer", "description": "Ending X coordinate."},
                "end_y": {"type": "integer", "description": "Ending Y coordinate."},
                "button": {
                    "type": "string",
                    "enum": ["left", "right", "middle"],
                    "default": "left",
                },
                "duration": {
                    "type": "number",
                    "description": "Drag duration in seconds.",
                    "default": 0.5,
                },
            },
            "required": ["start_x", "start_y", "end_x", "end_y"],
        }

    async def _execute_checked(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        import pyautogui

        pyautogui.PAUSE = 0.05
        sx = int(args["start_x"])
        sy = int(args["start_y"])
        ex = int(args["end_x"])
        ey = int(args["end_y"])
        button = str(args.get("button", "left"))
        duration = float(args.get("duration", 0.5))
        pyautogui.moveTo(sx, sy)
        pyautogui.drag(ex - sx, ey - sy, button=button, duration=duration)
        return ToolCallResult(
            ok=True, data={"start": {"x": sx, "y": sy}, "end": {"x": ex, "y": ey}, "button": button}
        )


class ScreenLocateTool(_ComputerTool):
    """Locate an image on screen and return its coordinates."""

    name = "screen.locate"
    description = "Find an image on the screen and return its bounding box and center coordinates."
    risk = RiskLevel.NONE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "image_path": {
                    "type": "string",
                    "description": "Path to the reference image (PNG) to locate on screen.",
                },
                "confidence": {
                    "type": "number",
                    "description": "Matching confidence threshold (0.0-1.0).",
                    "default": 0.8,
                },
            },
            "required": ["image_path"],
        }

    async def _execute_checked(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        import pyautogui

        raw_path = str(args["image_path"])
        confidence = float(args.get("confidence", 0.8))
        from .builtin import _confine

        ref = _confine(raw_path, ctx.workspace)
        if not ref.exists():
            return ToolCallResult(ok=False, error=f"Reference image not found: {raw_path}")
        region = pyautogui.locateOnScreen(str(ref), confidence=confidence)
        if region is None:
            return ToolCallResult(ok=False, error=f"Could not find image on screen: {raw_path}")
        left, top, width, height = region
        center = (left + width // 2, top + height // 2)
        return ToolCallResult(
            ok=True,
            data={
                "left": left,
                "top": top,
                "width": width,
                "height": height,
                "center_x": center[0],
                "center_y": center[1],
                "found": True,
            },
        )


class WindowFocusTool(_ComputerTool):
    """Bring a window to the foreground by title substring."""

    name = "window.focus"
    description = "Bring a window matching the given title substring to the foreground."
    risk = RiskLevel.DESTRUCTIVE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Substring to match against visible window titles.",
                },
            },
            "required": ["title"],
        }

    async def _execute_checked(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        import ctypes
        from ctypes import wintypes

        title_sub = str(args["title"]).lower()

        EnumWindows = ctypes.windll.user32.EnumWindows  # type: ignore[attr-defined]
        GetWindowTextW = ctypes.windll.user32.GetWindowTextW  # type: ignore[attr-defined]
        IsWindowVisible = ctypes.windll.user32.IsWindowVisible  # type: ignore[attr-defined]
        SetForegroundWindow = ctypes.windll.user32.SetForegroundWindow  # type: ignore[attr-defined]
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)  # type: ignore[attr-defined]

        found = None

        def _callback(hwnd: int, _lparam: int) -> bool:
            nonlocal found
            if IsWindowVisible(hwnd):
                length = GetWindowTextW(hwnd, None, 0)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    GetWindowTextW(hwnd, buf, length + 1)
                    if title_sub in buf.value.lower():
                        found = hwnd
                        return False
            return True

        EnumWindows(WNDENUMPROC(_callback), 0)
        if found is None:
            return ToolCallResult(ok=False, error=f"No visible window matching {title_sub!r}.")
        SetForegroundWindow(found)
        return ToolCallResult(ok=True, data={"title": title_sub, "focused": True})


class WindowCloseTool(_ComputerTool):
    """Close a window by title substring."""

    name = "window.close"
    description = "Close a window matching the given title substring."
    risk = RiskLevel.DESTRUCTIVE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Substring to match against visible window titles.",
                },
            },
            "required": ["title"],
        }

    async def _execute_checked(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        import ctypes
        from ctypes import wintypes

        title_sub = str(args["title"]).lower()

        EnumWindows = ctypes.windll.user32.EnumWindows  # type: ignore[attr-defined]
        GetWindowTextW = ctypes.windll.user32.GetWindowTextW  # type: ignore[attr-defined]
        IsWindowVisible = ctypes.windll.user32.IsWindowVisible  # type: ignore[attr-defined]
        PostMessageW = ctypes.windll.user32.PostMessageW  # type: ignore[attr-defined]
        WM_CLOSE = 0x0010
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)  # type: ignore[attr-defined]

        closed = []

        def _callback(hwnd: int, _lparam: int) -> bool:
            if IsWindowVisible(hwnd):
                length = GetWindowTextW(hwnd, None, 0)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    GetWindowTextW(hwnd, buf, length + 1)
                    if title_sub in buf.value.lower():
                        PostMessageW(hwnd, WM_CLOSE, 0, 0)
                        closed.append(buf.value)
            return True

        EnumWindows(WNDENUMPROC(_callback), 0)
        if not closed:
            return ToolCallResult(ok=False, error=f"No visible window matching {title_sub!r}.")
        return ToolCallResult(ok=True, data={"closed": closed, "count": len(closed)})


class WindowResizeTool(_ComputerTool):
    """Resize and reposition a window."""

    name = "window.resize"
    description = "Move and resize a window matching the given title substring."
    risk = RiskLevel.DESTRUCTIVE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Substring to match against visible window titles.",
                },
                "left": {"type": "integer", "description": "New left position."},
                "top": {"type": "integer", "description": "New top position."},
                "width": {"type": "integer", "description": "New width in pixels."},
                "height": {"type": "integer", "description": "New height in pixels."},
            },
            "required": ["title", "left", "top", "width", "height"],
        }

    async def _execute_checked(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        import ctypes
        from ctypes import wintypes

        title_sub = str(args["title"]).lower()
        left = int(args["left"])
        top = int(args["top"])
        width = int(args["width"])
        height = int(args["height"])

        EnumWindows = ctypes.windll.user32.EnumWindows  # type: ignore[attr-defined]
        GetWindowTextW = ctypes.windll.user32.GetWindowTextW  # type: ignore[attr-defined]
        IsWindowVisible = ctypes.windll.user32.IsWindowVisible  # type: ignore[attr-defined]
        MoveWindow = ctypes.windll.user32.MoveWindow  # type: ignore[attr-defined]
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)  # type: ignore[attr-defined]

        found = None

        def _callback(hwnd: int, _lparam: int) -> bool:
            nonlocal found
            if IsWindowVisible(hwnd):
                length = GetWindowTextW(hwnd, None, 0)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    GetWindowTextW(hwnd, buf, length + 1)
                    if title_sub in buf.value.lower():
                        found = hwnd
                        return False
            return True

        EnumWindows(WNDENUMPROC(_callback), 0)
        if found is None:
            return ToolCallResult(ok=False, error=f"No visible window matching {title_sub!r}.")
        MoveWindow(found, left, top, width, height, True)
        return ToolCallResult(
            ok=True,
            data={"title": title_sub, "left": left, "top": top, "width": width, "height": height},
        )
