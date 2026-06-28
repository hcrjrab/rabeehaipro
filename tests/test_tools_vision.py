"""Vision tool tests — schema, risk, and error paths."""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from rabeeh_core.config.schemas import RiskLevel, ToolCallResult
from rabeeh_core.tools.base import ToolContext
from rabeeh_core.tools.vision import OcrTool, ScreenReadTool, ScreenshotTool


def _ctx(workspace: str) -> ToolContext:
    return ToolContext(task_id=uuid4(), session_id=uuid4(), workspace=workspace)


# ---------------------------------------------------------------------------
# Attribute / schema tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_cls, name, risk",
    [
        (ScreenshotTool, "screenshot.capture", RiskLevel.NONE),
        (OcrTool, "vision.ocr", RiskLevel.NONE),
        (ScreenReadTool, "screen.read", RiskLevel.NONE),
    ],
)
def test_vision_tool_attributes(tool_cls, name, risk) -> None:
    assert tool_cls.name == name
    assert tool_cls.risk is risk
    assert tool_cls.description


def _check_schema_contains(tool, expected) -> None:
    schema = tool.schema()
    assert schema["type"] == "object"
    for key, val in expected.items():
        if key == "required":
            assert set(schema.get(key, [])) == set(val), f"{tool.__class__.__name__} {key}"
        elif key == "properties":
            for prop_name, prop_def in val.items():
                for pk, pv in prop_def.items():
                    assert (
                        schema[key][prop_name][pk] == pv
                    ), f"{tool.__class__.__name__}.{key}.{prop_name}.{pk}"


@pytest.mark.parametrize(
    "tool_cls, expected",
    [
        (
            ScreenshotTool,
            {"properties": {"path": {"type": "string"}, "monitor": {"type": "integer"}}},
        ),
        (
            OcrTool,
            {
                "required": ["path"],
                "properties": {"path": {"type": "string"}, "languages": {"type": "array"}},
            },
        ),
        (
            ScreenReadTool,
            {"properties": {"monitor": {"type": "integer"}}},
        ),
    ],
)
def test_vision_tool_schema(tool_cls, expected) -> None:
    _check_schema_contains(tool_cls(), expected)


# ---------------------------------------------------------------------------
# Screenshot tests (mock PIL ImageGrab to prevent actual screen capture)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screenshot_captures_to_path(tmp_path) -> None:
    with patch("PIL.ImageGrab.grab") as mock_grab:
        import PIL.Image as PImage

        mock_grab.return_value = PImage.new("RGB", (640, 480))
        tool = ScreenshotTool()
        out = await tool.execute({"path": "shot.png"}, _ctx(str(tmp_path)))
    assert out.ok
    assert out.data["path"] == "shot.png"
    assert out.data["width"] == 640
    assert out.data["height"] == 480


@pytest.mark.asyncio
async def test_screenshot_auto_path(tmp_path) -> None:
    with patch("PIL.ImageGrab.grab") as mock_grab:
        import PIL.Image as PImage

        mock_grab.return_value = PImage.new("RGB", (800, 600))
        tool = ScreenshotTool()
        out = await tool.execute({}, _ctx(str(tmp_path)))
    assert out.ok
    assert out.data["path"].startswith("screenshots/screen_")


@pytest.mark.asyncio
async def test_screenshot_exception_returns_error(tmp_path) -> None:
    with patch("PIL.ImageGrab.grab", side_effect=RuntimeError("mock failure")):
        tool = ScreenshotTool()
        out = await tool.execute({"path": "fail.png"}, _ctx(str(tmp_path)))
    assert not out.ok
    assert "Screenshot failed" in (out.error or "")


# ---------------------------------------------------------------------------
# OCR tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ocr_missing_path(tmp_path) -> None:
    tool = OcrTool()
    out = await tool.execute({}, _ctx(str(tmp_path)))
    assert not out.ok
    assert "Missing 'path'" in (out.error or "")


@pytest.mark.asyncio
async def test_ocr_file_not_found(tmp_path) -> None:
    tool = OcrTool()
    out = await tool.execute({"path": "no_such_image.png"}, _ctx(str(tmp_path)))
    assert not out.ok
    assert "not found" in (out.error or "")


# ---------------------------------------------------------------------------
# Multi-monitor screenshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screenshot_multi_monitor(tmp_path) -> None:
    with patch("PIL.ImageGrab.grab") as mock_grab:
        import PIL.Image as PImage

        mock_grab.return_value = PImage.new("RGB", (3200, 1080))
        tool = ScreenshotTool()
        out = await tool.execute({"monitor": 1}, _ctx(str(tmp_path)))
    assert out.ok


# ---------------------------------------------------------------------------
# OCR with mocked easyocr
# ---------------------------------------------------------------------------


_OCR_RESULTS = [
    ([10, 10, 100, 10, 100, 30, 10, 30], "Hello", 0.95),
    ([200, 10, 300, 10, 300, 30, 200, 30], "World", 0.90),
]


class _MockOCRReader:
    def __init__(self, *args, **kwargs):
        pass

    def readtext(self, path):
        return _OCR_RESULTS


@pytest.fixture()
def _mock_easyocr():
    """Add a fake easyocr module to sys.modules so OcrTool can import it."""
    import sys
    import types

    mock_mod = types.ModuleType("easyocr")
    mock_mod.Reader = _MockOCRReader
    sys.modules["easyocr"] = mock_mod
    yield
    sys.modules.pop("easyocr", None)


@pytest.mark.asyncio
async def test_ocr_with_mock_reader(tmp_path, _mock_easyocr) -> None:
    (tmp_path / "img.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    tool = OcrTool()
    out = await tool.execute({"path": "img.png"}, _ctx(str(tmp_path)))
    assert out.ok
    assert out.data["text"] == "Hello World"
    assert out.data["count"] == 2
    assert out.data["regions"][0]["confidence"] == 0.95


@pytest.mark.asyncio
async def test_ocr_with_languages(tmp_path, _mock_easyocr) -> None:
    (tmp_path / "img2.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    tool = OcrTool()
    out = await tool.execute({"path": "img2.png", "languages": ["en", "ar"]}, _ctx(str(tmp_path)))
    assert out.ok


@pytest.mark.asyncio
async def test_ocr_reader_exception(tmp_path, _mock_easyocr) -> None:
    import sys

    (tmp_path / "img3.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    reader_cls = sys.modules["easyocr"].Reader
    orig_readtext = reader_cls.readtext

    def failing_readtext(self, path):
        raise RuntimeError("mock failure")

    reader_cls.readtext = failing_readtext
    try:
        tool = OcrTool()
        out = await tool.execute({"path": "img3.png"}, _ctx(str(tmp_path)))
        assert not out.ok
        assert "OCR failed" in (out.error or "")
    finally:
        reader_cls.readtext = orig_readtext


# ---------------------------------------------------------------------------
# ScreenRead tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screen_read_cleans_temp_file(tmp_path) -> None:
    with patch.object(
        ScreenshotTool, "execute", return_value=ToolCallResult(ok=False, error="mock fail")
    ):
        tool = ScreenReadTool()
        out = await tool.execute({"monitor": 0}, _ctx(str(tmp_path)))
    assert not out.ok
    assert not (tmp_path / "_screen_read_temp.png").exists()


@pytest.mark.asyncio
async def test_screen_read_propagates_screenshot_error(tmp_path) -> None:
    with patch.object(
        ScreenshotTool, "execute", return_value=ToolCallResult(ok=False, error="mock fail")
    ):
        tool = ScreenReadTool()
        out = await tool.execute({"monitor": 0}, _ctx(str(tmp_path)))
    assert not out.ok


@pytest.mark.asyncio
async def test_screen_read_full_success(tmp_path) -> None:
    shot_ok = ToolCallResult(
        ok=True, data={"path": "_screen_read_temp.png", "width": 100, "height": 100}
    )
    ocr_ok = ToolCallResult(
        ok=True, data={"text": "extracted text", "regions": [{"text": "hello", "confidence": 0.9}]}
    )
    with (
        patch.object(ScreenshotTool, "execute", return_value=shot_ok),
        patch.object(OcrTool, "execute", return_value=ocr_ok),
    ):
        tool = ScreenReadTool()
        out = await tool.execute({"monitor": 0}, _ctx(str(tmp_path)))
    assert out.ok
    assert out.data["text"] == "extracted text"
