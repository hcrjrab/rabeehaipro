"""Office agent.

Creates documents (Word, Excel, PowerPoint, PDF) from a natural-language
request. It asks the LLM to choose the appropriate format and author the
content, then proposes the matching ``office.*`` / ``pdf.create`` tool call.

The agent is a *one-shot* document generator: a single LLM call decides the
format + content, a single SAFE tool call produces the file, and the step is
done. It deliberately avoids risky operations (no deletion, no overwrite of
existing work without explicit naming) — every tool it proposes is reversible.

Design
------
- The LLM returns a strict JSON action contract (see :func:`_run`).
- Default path is derived from the task id so two unrelated requests never
  collide; the model is free to rename via the ``path`` field.
- All proposed tools are risk ``SAFE`` (file creation only), so this agent
  never triggers the approval gate.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config.schemas import AgentRole, RiskLevel, ToolCallRequest
from ..llm.base import LLMMessage
from .base import AgentContext, AgentResult, BaseAgent, _parse_action_json

_log = logging.getLogger(__name__)

# Maps the LLM's chosen format -> the tool it triggers.
_FORMAT_TO_TOOL: dict[str, str] = {
    "word": "office.create_word",
    "docx": "office.create_word",
    "excel": "office.create_excel",
    "xlsx": "office.create_excel",
    "spreadsheet": "office.create_excel",
    "powerpoint": "office.create_powerpoint",
    "pptx": "office.create_powerpoint",
    "slides": "office.create_powerpoint",
    "pdf": "pdf.create",
}

_VALID_ACTIONS = {"create"} | set(_FORMAT_TO_TOOL)


class OfficeAgent(BaseAgent):
    """Document-generation specialist (Word / Excel / PowerPoint / PDF)."""

    role = AgentRole.OFFICE

    def system_prompt(self) -> str:
        return (
            "You are the Office agent. You create polished business documents "
            "(Word, Excel, PowerPoint, PDF) from a user request. Choose the most "
            "appropriate format and author complete, professional content. "
            "Respond with ONLY a JSON object matching exactly this schema, "
            "no markdown fences, no commentary:\n"
            "{\n"
            '  "action": "create",\n'
            '  "format": "<word | excel | powerpoint | pdf>",\n'
            '  "path": "<output filename, e.g. report.docx>",\n'
            '  "title": "<document title>",\n'
            '  "sections": [{"heading": "...", "body": "..."}],\n'
            '  "headers": ["..."],          // excel only\n'
            '  "rows": [["...","..."]],     // excel only\n'
            '  "slides": [{"title":"...","content":"..."}]  // powerpoint only\n'
            "}"
        )

    async def _run(self, ctx: AgentContext) -> AgentResult:
        """Ask the LLM what to create, then propose the matching tool call.

        If the step has already produced a file (``office_done`` flag set),
        the agent reports completion instead of regenerating.
        """
        if ctx.scratchpad.get("office_done"):
            path = ctx.scratchpad.get("office_path", "document")
            return AgentResult(
                message=f"Document already created: {path}",
                done=True,
            )

        messages = ctx.to_llm_messages(self.system_prompt())
        messages.append(
            LLMMessage(
                role="user",
                content=(
                    f"Task: {ctx.scratchpad.get('step', ctx.goal)}\n"
                    "Decide the document format and author its full content."
                ),
            )
        )
        response = await self.llm.chat(messages, temperature=0.2)
        decision = _parse_action_json(
            response.content, valid_actions=_VALID_ACTIONS, fallback="create"
        )

        fmt = str(decision.get("format", "word")).lower().strip()
        tool_name = _FORMAT_TO_TOOL.get(fmt, "office.create_word")
        arguments = _build_arguments(decision, ctx)

        ctx.scratchpad["office_done"] = True
        ctx.scratchpad["office_path"] = arguments["path"]

        return AgentResult(
            message=f"Creating {fmt} document: {arguments['path']}",
            tool_call=ToolCallRequest(
                tool_name=tool_name,
                arguments=arguments,
                risk=RiskLevel.SAFE,
                rationale=f"Generate the requested {fmt} document.",
            ),
        )


def _build_arguments(decision: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
    """Translate the LLM decision into the tool's argument dict."""
    fmt = str(decision.get("format", "word")).lower().strip()
    title = str(decision.get("title", ctx.scratchpad.get("step", "Untitled")[:80]))
    path = str(decision.get("path", "")).strip()
    if not path:
        ext = {"excel": "xlsx", "powerpoint": "pptx", "pdf": "pdf"}.get(fmt, "docx")
        path = f"generated/{ctx.task_id}.{ext}"

    base: dict[str, Any] = {"path": path, "title": title}

    if fmt in {"excel", "xlsx", "spreadsheet"}:
        base["headers"] = decision.get("headers") or _default_headers(title)
        base["rows"] = decision.get("rows") or []
        base["title"] = title[:31]  # Excel sheet-name limit
    elif fmt in {"powerpoint", "pptx", "slides"}:
        base["slides"] = decision.get("slides") or []
    else:
        base["sections"] = decision.get("sections") or [
            {"heading": title, "body": str(decision.get("body", ""))}
        ]

    return base


def _default_headers(title: str) -> list[str]:
    """Sensible default column headers when the model omits them."""
    return ["Item", "Description", "Quantity", "Price"]
