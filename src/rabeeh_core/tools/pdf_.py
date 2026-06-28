"""PDF tools — create and read PDF files.

Two capabilities:
- ``pdf.create``  -> generate a PDF from structured content (reportlab).
- ``pdf.read``    -> extract all text from an existing PDF (pypdf).

Both are workspace-confined. The PDF libraries are imported lazily so the
app boots without the ``pdf`` extra.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config.schemas import RiskLevel, ToolCallResult
from .base import BaseTool, ToolContext
from .builtin import _confine


class _PdfTool(BaseTool):
    """Shared base for PDF tools: common resolve + error-handling pattern."""

    risk = RiskLevel.SAFE

    def _resolve(self, args: dict[str, Any], ctx: ToolContext) -> tuple[Path, str]:
        raw_path = str(args.get("path", "")).strip()
        if not raw_path:
            raise ValueError("Missing 'path' argument.")
        return _confine(raw_path, ctx.workspace), raw_path

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        try:
            return await self._execute_checked(args, ctx)
        except ValueError as exc:
            return ToolCallResult(ok=False, error=str(exc))
        except ImportError as exc:
            return ToolCallResult(
                ok=False,
                error=f"Missing dependency: {exc}. Install the 'pdf' extra: pip install rabeeh-ai-agent-pro[pdf]",
            )
        except Exception as exc:
            return ToolCallResult(ok=False, error=f"PDF tool error: {exc}")

    async def _execute_checked(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        raise NotImplementedError


class CreatePdfTool(_PdfTool):
    """Create a PDF document with a title and paragraphs."""

    name = "pdf.create"
    description = "Create a PDF document with a title, optional subtitle, and body text."
    risk = RiskLevel.SAFE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Output .pdf path (relative)."},
                "title": {"type": "string", "description": "Document title."},
                "subtitle": {"type": "string", "description": "Optional subtitle."},
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "heading": {"type": "string"},
                            "body": {"type": "string"},
                        },
                    },
                    "description": "Content sections with optional headings.",
                },
            },
            "required": ["path", "title"],
        }

    async def _execute_checked(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        target, raw_path = self._resolve(args, ctx)
        title = str(args.get("title", "Untitled"))
        subtitle = str(args.get("subtitle", ""))
        sections = args.get("sections") or []

        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(str(target), pagesize=letter)
        story: list[Any] = [
            Paragraph(title, styles["Title"]),
        ]
        if subtitle:
            story.append(Paragraph(subtitle, styles["Normal"]))
            story.append(Spacer(1, 0.2 * inch))
        for sec in sections:
            heading = str(sec.get("heading", ""))
            body = str(sec.get("body", ""))
            if heading:
                story.append(Paragraph(heading, styles["Heading2"]))
            if body:
                story.append(Paragraph(body, styles["Normal"]))

        target.parent.mkdir(parents=True, exist_ok=True)
        doc.build(story)
        return ToolCallResult(
            ok=True,
            data={"path": raw_path, "title": title, "sections": len(sections)},
        )


class ReadPdfTool(_PdfTool):
    """Extract all text from an existing PDF file."""

    name = "pdf.read"
    description = "Read and extract text from a PDF file inside the workspace."
    risk = RiskLevel.NONE

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path inside workspace."}
            },
            "required": ["path"],
        }

    async def _execute_checked(self, args: dict[str, Any], ctx: ToolContext) -> ToolCallResult:
        from pypdf import PdfReader

        target, raw_path = self._resolve(args, ctx)
        if not target.exists():
            return ToolCallResult(ok=False, error=f"File not found: {raw_path}")

        reader = PdfReader(str(target))
        pages: list[str] = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)

        full_text = "\n\n".join(pages)
        return ToolCallResult(
            ok=True,
            data={
                "path": raw_path,
                "pages": len(pages),
                "text": full_text,
                "chars": len(full_text),
            },
        )
