"""Computer-use tool tests — schema, risk, and error-handling paths."""

from __future__ import annotations

from uuid import uuid4

import pytest

from rabeeh_core.config.schemas import RiskLevel
from rabeeh_core.tools.base import ToolContext
from rabeeh_core.tools.computer import (
    ClipboardTool,
    KeyboardTypeTool,
    MouseClickTool,
    MouseDragTool,
    MouseMoveTool,
    MouseScrollTool,
    ScreenLocateTool,
    WindowCloseTool,
    WindowFocusTool,
    WindowListTool,
    WindowResizeTool,
)


def _ctx(workspace: str) -> ToolContext:
    return ToolContext(task_id=uuid4(), session_id=uuid4(), workspace=workspace)


@pytest.mark.parametrize(
    "tool_cls, name, risk",
    [
        (MouseClickTool, "mouse.click", RiskLevel.SAFE),
        (MouseMoveTool, "mouse.move", RiskLevel.SAFE),
        (MouseScrollTool, "mouse.scroll", RiskLevel.SAFE),
        (MouseDragTool, "mouse.drag", RiskLevel.SAFE),
        (KeyboardTypeTool, "keyboard.type", RiskLevel.DESTRUCTIVE),
        (ClipboardTool, "clipboard", RiskLevel.SAFE),
        (WindowListTool, "window.list", RiskLevel.NONE),
        (WindowFocusTool, "window.focus", RiskLevel.DESTRUCTIVE),
        (WindowCloseTool, "window.close", RiskLevel.DESTRUCTIVE),
        (WindowResizeTool, "window.resize", RiskLevel.DESTRUCTIVE),
        (ScreenLocateTool, "screen.locate", RiskLevel.NONE),
    ],
)
def test_computer_tool_attributes(tool_cls, name, risk) -> None:
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
            MouseClickTool,
            {
                "required": ["x", "y"],
                "properties": {
                    "x": {"type": "integer"},
                    "button": {"enum": ["left", "right", "middle"]},
                },
            },
        ),
        (
            MouseMoveTool,
            {
                "required": ["x", "y"],
                "properties": {"x": {"type": "integer"}, "duration": {"type": "number"}},
            },
        ),
        (
            MouseScrollTool,
            {
                "properties": {"clicks": {"type": "integer"}},
            },
        ),
        (
            KeyboardTypeTool,
            {
                "properties": {"text": {"type": "string"}, "keys": {"type": "string"}},
            },
        ),
        (
            ClipboardTool,
            {
                "required": ["action"],
                "properties": {"action": {"enum": ["read", "write"]}},
            },
        ),
        (
            WindowListTool,
            {
                "properties": {},
            },
        ),
        (
            ScreenLocateTool,
            {
                "required": ["image_path"],
                "properties": {"confidence": {"type": "number"}},
            },
        ),
    ],
)
def test_computer_tool_schema(tool_cls, expected) -> None:
    _check_schema_contains(tool_cls(), expected)


@pytest.mark.asyncio
async def test_keyboard_type_missing_args(tmp_path) -> None:
    tool = KeyboardTypeTool()
    out = await tool.execute({}, _ctx(str(tmp_path)))
    assert not out.ok
    assert out.error  # either "Provide either 'text' or 'keys'." or a computer-use error


@pytest.mark.asyncio
async def test_screen_locate_no_image(tmp_path) -> None:
    tool = ScreenLocateTool()
    out = await tool.execute({"image_path": "nonexistent.png"}, _ctx(str(tmp_path)))
    assert not out.ok


@pytest.mark.asyncio
async def test_window_focus_no_match(tmp_path) -> None:
    tool = WindowFocusTool()
    out = await tool.execute({"title": "ZZZZ_NO_WINDOW_LIKE_THIS_98765"}, _ctx(str(tmp_path)))
    assert not out.ok


@pytest.mark.asyncio
async def test_window_close_no_match(tmp_path) -> None:
    tool = WindowCloseTool()
    out = await tool.execute({"title": "ZZZZ_NO_WINDOW_LIKE_THIS_98765"}, _ctx(str(tmp_path)))
    assert not out.ok
