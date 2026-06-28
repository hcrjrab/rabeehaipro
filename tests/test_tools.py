"""Tool registry + built-in tools tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from rabeeh_core.config.schemas import RiskLevel
from rabeeh_core.tools.base import ToolContext
from rabeeh_core.tools.builtin import EchoTool, ListDirTool, ReadTextTool
from rabeeh_core.tools.registry import ToolRegistry


def _ctx(workspace: str) -> ToolContext:
    return ToolContext(task_id=uuid4(), session_id=uuid4(), workspace=workspace)


def test_registry_register_and_lookup() -> None:
    """Registered tools must be findable by name and enumerated."""
    reg = ToolRegistry()
    reg.register(EchoTool())
    assert "echo" in reg
    assert reg.get("echo") is not None
    assert reg.get("missing") is None
    assert reg.require("echo").name == "echo"
    with pytest.raises(KeyError):
        reg.require("nope")


def test_registry_function_schemas_are_well_formed() -> None:
    """``function_schemas`` must emit OpenAI tool descriptors."""
    reg = ToolRegistry()
    reg.register(EchoTool())
    schemas = reg.function_schemas()
    assert schemas and schemas[0]["type"] == "function"
    assert schemas[0]["function"]["name"] == "echo"


@pytest.mark.asyncio
async def test_echo_tool_returns_input(tmp_path) -> None:
    tool = EchoTool()
    out = await tool.execute({"message": "ping"}, _ctx(str(tmp_path)))
    assert out.ok and out.data == {"echo": "ping"}


@pytest.mark.asyncio
async def test_read_text_tool_confines_to_workspace(tmp_path) -> None:
    """Read tool must (a) read inside the workspace and (b) reject escapes."""
    (tmp_path / "hello.txt").write_text("hi there", encoding="utf-8")
    tool = ReadTextTool()
    ok = await tool.execute({"path": "hello.txt"}, _ctx(str(tmp_path)))
    assert ok.ok and ok.data["content"] == "hi there"

    bad = await tool.execute({"path": "../escape.txt"}, _ctx(str(tmp_path)))
    assert not bad.ok and "escapes" in (bad.error or "")


@pytest.mark.asyncio
async def test_list_dir_tool_lists_entries(tmp_path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    tool = ListDirTool()
    out = await tool.execute({"path": ""}, _ctx(str(tmp_path)))
    assert out.ok
    names = {e["name"] for e in out.data["entries"]}
    assert {"sub", "a.txt"} <= names


def test_builtin_risk_classifications() -> None:
    """All default tools must be classified as NONE risk (read-only)."""
    for cls in (EchoTool, ReadTextTool, ListDirTool):
        assert cls.risk is RiskLevel.NONE, cls.__name__
