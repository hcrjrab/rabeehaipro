"""File tool tests (write, delete, copy, move) + Office/PDF tool tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from rabeeh_core.config.schemas import RiskLevel
from rabeeh_core.tools.base import ToolContext
from rabeeh_core.tools.file import CopyFileTool, DeleteFileTool, MoveFileTool, WriteTextTool


def _ctx(workspace: str) -> ToolContext:
    return ToolContext(task_id=uuid4(), session_id=uuid4(), workspace=workspace)


# ---------------------------------------------------------------------------
# File write tool
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_write_creates_file(tmp_path) -> None:
    tool = WriteTextTool()
    out = await tool.execute({"path": "sub/hello.txt", "content": "world"}, _ctx(str(tmp_path)))
    assert out.ok
    assert (tmp_path / "sub" / "hello.txt").read_text(encoding="utf-8") == "world"


@pytest.mark.asyncio
async def test_write_overwrites_existing(tmp_path) -> None:
    p = tmp_path / "f.txt"
    p.write_text("old", encoding="utf-8")
    tool = WriteTextTool()
    out = await tool.execute({"path": "f.txt", "content": "new"}, _ctx(str(tmp_path)))
    assert out.ok and p.read_text(encoding="utf-8") == "new"


@pytest.mark.asyncio
async def test_write_rejects_workspace_escape(tmp_path) -> None:
    tool = WriteTextTool()
    out = await tool.execute({"path": "../escape.txt", "content": "x"}, _ctx(str(tmp_path)))
    assert not out.ok and "escapes" in (out.error or "")


# ---------------------------------------------------------------------------
# File delete tool
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_delete_removes_file(tmp_path) -> None:
    p = tmp_path / "delme.txt"
    p.write_text("bye", encoding="utf-8")
    tool = DeleteFileTool()
    out = await tool.execute({"path": "delme.txt"}, _ctx(str(tmp_path)))
    assert out.ok and not p.exists()


@pytest.mark.asyncio
async def test_delete_removes_directory(tmp_path) -> None:
    d = tmp_path / "dir"
    d.mkdir()
    (d / "child.txt").write_text("x", encoding="utf-8")
    tool = DeleteFileTool()
    out = await tool.execute({"path": "dir"}, _ctx(str(tmp_path)))
    assert out.ok and not d.exists()


@pytest.mark.asyncio
async def test_delete_missing_file_fails(tmp_path) -> None:
    tool = DeleteFileTool()
    out = await tool.execute({"path": "nope.txt"}, _ctx(str(tmp_path)))
    assert not out.ok and "Not found" in (out.error or "")


# ---------------------------------------------------------------------------
# File copy tool
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_copy_file(tmp_path) -> None:
    (tmp_path / "a.txt").write_text("copy me", encoding="utf-8")
    tool = CopyFileTool()
    out = await tool.execute({"source": "a.txt", "destination": "b.txt"}, _ctx(str(tmp_path)))
    assert out.ok and (tmp_path / "b.txt").read_text(encoding="utf-8") == "copy me"


@pytest.mark.asyncio
async def test_copy_directory(tmp_path) -> None:
    d = tmp_path / "src_dir"
    d.mkdir()
    (d / "x.txt").write_text("y", encoding="utf-8")
    tool = CopyFileTool()
    out = await tool.execute({"source": "src_dir", "destination": "dst_dir"}, _ctx(str(tmp_path)))
    assert out.ok and (tmp_path / "dst_dir" / "x.txt").read_text(encoding="utf-8") == "y"


# ---------------------------------------------------------------------------
# File move tool
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_move_file(tmp_path) -> None:
    (tmp_path / "a.txt").write_text("move me", encoding="utf-8")
    tool = MoveFileTool()
    out = await tool.execute({"source": "a.txt", "destination": "sub/b.txt"}, _ctx(str(tmp_path)))
    assert out.ok
    assert not (tmp_path / "a.txt").exists()
    assert (tmp_path / "sub" / "b.txt").read_text(encoding="utf-8") == "move me"


# ---------------------------------------------------------------------------
# Risk classifications
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "cls, risk",
    [
        (WriteTextTool, RiskLevel.SAFE),
        (CopyFileTool, RiskLevel.SAFE),
        (DeleteFileTool, RiskLevel.DESTRUCTIVE),
        (MoveFileTool, RiskLevel.DESTRUCTIVE),
    ],
)
def test_file_tool_risk(cls, risk) -> None:
    assert cls.risk is risk


# ---------------------------------------------------------------------------
# Office tools (skipped gracefully if deps missing)
# ---------------------------------------------------------------------------
def _try_import_office() -> bool:
    try:
        import docx  # noqa: F401
        import openpyxl  # noqa: F401
        import pptx  # noqa: F401

        return True
    except ImportError:
        return False


_office = pytest.mark.skipif(not _try_import_office(), reason="office extras not installed")


@_office
@pytest.mark.asyncio
async def test_create_word(tmp_path) -> None:
    from rabeeh_core.tools.office import CreateWordTool

    tool = CreateWordTool()
    out = await tool.execute(
        {
            "path": "doc.docx",
            "title": "Test Doc",
            "sections": [
                {"heading": "Intro", "body": "Hello world"},
            ],
        },
        _ctx(str(tmp_path)),
    )
    assert out.ok and (tmp_path / "doc.docx").exists()


@_office
@pytest.mark.asyncio
async def test_create_excel(tmp_path) -> None:
    from rabeeh_core.tools.office import CreateExcelTool

    tool = CreateExcelTool()
    out = await tool.execute(
        {"path": "sheet.xlsx", "headers": ["Name", "Age"], "rows": [["Alice", 30]]},
        _ctx(str(tmp_path)),
    )
    assert out.ok and (tmp_path / "sheet.xlsx").exists()


@_office
@pytest.mark.asyncio
async def test_create_powerpoint(tmp_path) -> None:
    from rabeeh_core.tools.office import CreatePowerPointTool

    tool = CreatePowerPointTool()
    out = await tool.execute(
        {
            "path": "pres.pptx",
            "title": "Talk",
            "slides": [
                {"title": "Slide 1", "content": "Bullets"},
            ],
        },
        _ctx(str(tmp_path)),
    )
    assert out.ok and (tmp_path / "pres.pptx").exists()


# ---------------------------------------------------------------------------
# PDF tools (skipped gracefully if deps missing)
# ---------------------------------------------------------------------------
def _try_import_pdf() -> bool:
    try:
        import pypdf  # noqa: F401
        import reportlab  # noqa: F401

        return True
    except ImportError:
        return False


_pdf = pytest.mark.skipif(not _try_import_pdf(), reason="pdf extras not installed")


@_pdf
@pytest.mark.asyncio
async def test_create_pdf(tmp_path) -> None:
    from rabeeh_core.tools.pdf_ import CreatePdfTool

    tool = CreatePdfTool()
    out = await tool.execute(
        {
            "path": "doc.pdf",
            "title": "Report",
            "sections": [
                {"heading": "Section 1", "body": "Content here"},
            ],
        },
        _ctx(str(tmp_path)),
    )
    assert out.ok and (tmp_path / "doc.pdf").exists()


@_pdf
@pytest.mark.asyncio
async def test_read_pdf_roundtrip(tmp_path) -> None:
    from rabeeh_core.tools.pdf_ import CreatePdfTool, ReadPdfTool

    create = CreatePdfTool()
    c_out = await create.execute(
        {
            "path": "source.pdf",
            "title": "Source",
            "sections": [
                {"body": "Extractable text content"},
            ],
        },
        _ctx(str(tmp_path)),
    )
    assert c_out.ok

    read = ReadPdfTool()
    r_out = await read.execute({"path": "source.pdf"}, _ctx(str(tmp_path)))
    assert r_out.ok
    assert "Extractable text" in (r_out.data.get("text") or "")
