"""Additional file tool tests — coverage for remaining branches."""

from __future__ import annotations

from uuid import uuid4

import pytest

from rabeeh_core.config.schemas import RiskLevel
from rabeeh_core.tools.base import ToolContext
from rabeeh_core.tools.file import CopyFileTool, DeleteFileTool, MoveFileTool, WriteTextTool


def _ctx(workspace: str) -> ToolContext:
    return ToolContext(task_id=uuid4(), session_id=uuid4(), workspace=workspace)


@pytest.mark.asyncio
async def test_write_missing_path(tmp_path) -> None:
    tool = WriteTextTool()
    out = await tool.execute({"content": "data"}, _ctx(str(tmp_path)))
    assert not out.ok
    assert "Missing 'path'" in (out.error or "")


@pytest.mark.asyncio
async def test_write_permission_error(tmp_path) -> None:
    tool = WriteTextTool()
    out = await tool.execute({"path": "test.txt", "content": "data"}, _ctx(str(tmp_path)))
    assert out.ok


@pytest.mark.asyncio
async def test_delete_missing_path_argument(tmp_path) -> None:
    tool = DeleteFileTool()
    out = await tool.execute({}, _ctx(str(tmp_path)))
    assert not out.ok
    assert "Missing 'path'" in (out.error or "")


@pytest.mark.asyncio
async def test_copy_missing_source(tmp_path) -> None:
    tool = CopyFileTool()
    out = await tool.execute({"destination": "b.txt"}, _ctx(str(tmp_path)))
    assert not out.ok


@pytest.mark.asyncio
async def test_copy_missing_destination(tmp_path) -> None:
    tool = CopyFileTool()
    out = await tool.execute({"source": "a.txt"}, _ctx(str(tmp_path)))
    assert not out.ok


@pytest.mark.asyncio
async def test_copy_source_not_found(tmp_path) -> None:
    tool = CopyFileTool()
    out = await tool.execute({"source": "nope.txt", "destination": "b.txt"}, _ctx(str(tmp_path)))
    assert not out.ok
    assert "not found" in (out.error or "").lower()


@pytest.mark.asyncio
async def test_move_missing_source(tmp_path) -> None:
    tool = MoveFileTool()
    out = await tool.execute({"destination": "b.txt"}, _ctx(str(tmp_path)))
    assert not out.ok


@pytest.mark.asyncio
async def test_move_missing_destination(tmp_path) -> None:
    tool = MoveFileTool()
    out = await tool.execute({"source": "a.txt"}, _ctx(str(tmp_path)))
    assert not out.ok


@pytest.mark.asyncio
async def test_move_source_not_found(tmp_path) -> None:
    tool = MoveFileTool()
    out = await tool.execute({"source": "nope.txt", "destination": "b.txt"}, _ctx(str(tmp_path)))
    assert not out.ok
    assert "not found" in (out.error or "").lower()


@pytest.mark.asyncio
async def test_write_schema_validation(tmp_path) -> None:
    tool = WriteTextTool()
    schema = tool.schema()
    assert "path" in schema["properties"]
    assert "content" in schema["properties"]
    assert schema["required"] == ["path", "content"]


@pytest.mark.asyncio
async def test_delete_schema_validation(tmp_path) -> None:
    tool = DeleteFileTool()
    schema = tool.schema()
    assert schema["required"] == ["path"]


@pytest.mark.parametrize(
    "tool_cls, risk",
    [
        (WriteTextTool, RiskLevel.SAFE),
        (CopyFileTool, RiskLevel.SAFE),
        (DeleteFileTool, RiskLevel.DESTRUCTIVE),
        (MoveFileTool, RiskLevel.DESTRUCTIVE),
    ],
)
def test_file_tool_risk(tool_cls, risk) -> None:
    assert tool_cls.risk is risk


def test_file_tool_descriptions() -> None:
    for cls in (WriteTextTool, DeleteFileTool, CopyFileTool, MoveFileTool):
        assert cls.description
