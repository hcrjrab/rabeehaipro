"""Vision tools — screenshot, OCR, screen text extraction.

Tools:
- ``screenshot.capture``  -> take a screenshot of the full screen or a region.
- ``vision.ocr``          -> run OCR on a saved image file and return extracted text.
- ``screen.read``         -> capture + OCR in one step (convenience).

Dependencies (opencv-python, easyocr, pillow) are imported lazily.
On Windows, screenshots use the Win32 API via ``ctypes`` (no mss dependency).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..config.schemas import RiskLevel, ToolCallResult
from .base import BaseTool, ToolContext
from .builtin import _confine

_log = logging.getLogger(__name__)


class ScreenshotTool(BaseTool):
    """Capture the screen to a PNG file in the workspace."""

    name = "screenshot.capture"
    description = "Take a screenshot of the full screen and save it as PNG."
    risk = RiskLevel.NONE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Output PNG path (relative). Defaults to screenshots/screen_NNN.png.",
                },
                "monitor": {
                    "type": "integer",
                    "description": "Monitor index (0 = primary). Default 0.",
                },
            },
        }

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        try:
            from PIL import ImageGrab
        except ImportError:
            return ToolCallResult(
                ok=False,
                error="Pillow is required for screenshots. pip install pillow",
            )

        raw_path = str(args.get("path", "")).strip()
        monitor = int(args.get("monitor", 0))

        if not raw_path:
            # Auto-generate a path under screenshots/.
            screenshots_dir = Path(ctx.workspace) / "screenshots"
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            n = len(list(screenshots_dir.glob("screen_*.png")))
            raw_path = f"screenshots/screen_{n:04d}.png"

        target = _confine(raw_path, ctx.workspace)
        target.parent.mkdir(parents=True, exist_ok=True)

        try:
            if monitor == 0:
                img = ImageGrab.grab()
            else:
                # Multi-monitor: grab all and select by index.
                imgs = ImageGrab.grab(all_screens=True)
                # For simplicity on Windows, grab() with all_screens=True gets
                # the virtual screen. Per-monitor selection requires win32 API.
                img = imgs

            img.save(str(target), "PNG")
            return ToolCallResult(
                ok=True,
                data={
                    "path": raw_path,
                    "width": img.width,
                    "height": img.height,
                    "bytes": target.stat().st_size,
                },
            )
        except Exception as exc:
            return ToolCallResult(ok=False, error=f"Screenshot failed: {exc}")


class OcrTool(BaseTool):
    """Run OCR on an image file and return extracted text."""

    name = "vision.ocr"
    description = (
        "Run optical character recognition (OCR) on an image file and return the extracted text."
    )
    risk = RiskLevel.NONE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Image file path (relative to workspace).",
                },
                "languages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "OCR languages (default: ['en']). E.g. ['en', 'ar'].",
                },
            },
            "required": ["path"],
        }

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        raw_path = str(args.get("path", "")).strip()
        if not raw_path:
            return ToolCallResult(ok=False, error="Missing 'path' argument.")

        target = _confine(raw_path, ctx.workspace)
        if not target.exists():
            return ToolCallResult(ok=False, error=f"Image not found: {raw_path}")

        try:
            import easyocr
        except ImportError:
            return ToolCallResult(
                ok=False,
                error="EasyOCR is required. pip install easyocr",
            )

        languages = args.get("languages") or ["en"]
        try:
            reader = easyocr.Reader(languages, gpu=True, verbose=False)
            results = reader.readtext(str(target))
        except Exception as exc:
            return ToolCallResult(ok=False, error=f"OCR failed: {exc}")

        # Aggregate: full text + per-region results.
        full_text = " ".join(item[1] for item in results)
        regions = [
            {
                "text": item[1],
                "confidence": round(float(item[2]), 3),
                "bbox": [int(c) for c in item[0]],
            }
            for item in results
        ]
        return ToolCallResult(
            ok=True,
            data={"path": raw_path, "text": full_text, "regions": regions, "count": len(regions)},
        )


class ScreenReadTool(BaseTool):
    """Convenience tool: screenshot + OCR in one step."""

    name = "screen.read"
    description = (
        "Take a screenshot of the screen and immediately OCR it, returning the extracted text."
    )
    risk = RiskLevel.NONE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "monitor": {"type": "integer", "description": "Monitor index (default 0)."},
            },
        }

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        # Step 1: screenshot.
        shot = ScreenshotTool()
        shot_result = await shot.execute(
            {"path": "_screen_read_temp.png", "monitor": args.get("monitor", 0)},
            ctx,
        )
        if not shot_result.ok:
            return shot_result

        # Step 2: OCR on the captured image.
        ocr = OcrTool()
        ocr_result = await ocr.execute(
            {"path": "_screen_read_temp.png", "languages": args.get("languages")}, ctx
        )

        import contextlib

        temp = Path(ctx.workspace) / "_screen_read_temp.png"
        if temp.exists():
            with contextlib.suppress(OSError):
                temp.unlink()

        if not ocr_result.ok:
            return ocr_result

        return ToolCallResult(
            ok=True,
            data={
                "screenshot": shot_result.data,
                "text": ocr_result.data.get("text", ""),
                "regions": ocr_result.data.get("regions", []),
            },
        )
