from __future__ import annotations

import logging
from typing import Any

from ..config.schemas import AgentRole, RiskLevel, ToolCallRequest
from .base import AgentContext, AgentResult, BaseAgent

_log = logging.getLogger(__name__)


DOC_PROMPTS: dict[str, tuple[str, dict[str, Any]]] = {
    "quotation": (
        "Generate a professional quotation document with the following details.",
        {
            "title": "Quotation",
            "sections": [
                {"heading": "Quotation", "content": ""},
                {
                    "heading": "Terms & Conditions",
                    "content": "Standard terms apply. Payment due within 30 days.",
                },
            ],
        },
    ),
    "invoice": (
        "Generate a professional invoice document.",
        {
            "title": "Invoice",
            "sections": [
                {"heading": "Invoice", "content": ""},
                {"heading": "Payment Details", "content": "Bank transfer. Due within 30 days."},
            ],
        },
    ),
    "purchase_order": (
        "Generate a purchase order document.",
        {
            "title": "Purchase Order",
            "sections": [
                {"heading": "Purchase Order", "content": ""},
                {"heading": "Delivery & Payment Terms", "content": "Standard terms apply."},
            ],
        },
    ),
    "boq": (
        "Generate a Bill of Quantities spreadsheet.",
        {
            "title": "Bill of Quantities",
            "headers": ["Item #", "Description", "Quantity", "Unit", "Rate", "Amount"],
            "rows": [],
        },
    ),
    "estimation": (
        "Generate a material estimation spreadsheet.",
        {
            "title": "Material Estimation",
            "headers": ["Item #", "Material", "Specification", "Quantity", "Unit", "Remarks"],
            "rows": [],
        },
    ),
    "report": (
        "Generate a report document.",
        {
            "title": "Report",
            "sections": [{"heading": "Report", "content": ""}],
        },
    ),
}


class BusinessAgent(BaseAgent):
    """Agent for business process automation and document generation.

    Phase 7 implementation: uses the BusinessRepository for CRUD operations
    on customers, vendors, quotations, invoices, POs, BOQ, inventory, and
    electrical estimations. Delegates document output to office tools.
    """

    role: AgentRole = AgentRole.BUSINESS
    description: str = "Business document generation and process automation."

    def __init__(self) -> None:
        from ..business.repository import get_business_repository

        self._repo = get_business_repository()

    def system_prompt(self) -> str:
        return (
            "You are the Business Agent. You handle quotations, invoices, "
            "purchase orders, BOQs, inventory, CRM, vendor management, and "
            "electrical estimation. Persist data via the business repository "
            "and generate output documents using office tools."
        )

    async def _run(self, ctx: AgentContext) -> AgentResult:
        goal = ctx.goal.lower()

        if "create customer" in goal or "add customer" in goal:
            return await self._handle_create_customer(ctx.goal)

        if "list customers" in goal or "all customers" in goal:
            return await self._handle_list("customers")

        if "create vendor" in goal or "add vendor" in goal:
            return await self._handle_create_vendor(ctx.goal)

        if "list vendors" in goal or "all vendors" in goal:
            return await self._handle_list("vendors")

        if "summary" in goal or "dashboard" in goal:
            return await self._handle_summary()

        doc_type = self._detect_document_type(goal)
        if doc_type:
            return self._doc_result(doc_type, ctx.goal)

        # Default: try to create a generic business document.
        return AgentResult(
            message=f"Business request acknowledged: {ctx.goal[:200]}",
            tool_call=ToolCallRequest(
                tool_name="office.create_word",
                arguments={
                    "title": ctx.goal[:100],
                    "sections": [{"heading": "Document", "content": ctx.goal}],
                },
                rationale="Generate business document.",
                risk=RiskLevel.SAFE,
            ),
            done=False,
        )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    async def _handle_create_customer(self, goal: str) -> AgentResult:
        try:
            data = {
                "name": goal.replace("create customer", "").replace("add customer", "").strip()
                or "New Customer"
            }
            customer = await self._repo.create_customer(data)
            return AgentResult(
                message=f"Customer created: {customer['name']} ({customer['id']})",
                done=True,
            )
        except Exception as exc:
            return AgentResult(message=f"Failed to create customer: {exc}", done=True)

    async def _handle_create_vendor(self, goal: str) -> AgentResult:
        try:
            data = {
                "name": goal.replace("create vendor", "").replace("add vendor", "").strip()
                or "New Vendor"
            }
            vendor = await self._repo.create_vendor(data)
            return AgentResult(
                message=f"Vendor created: {vendor['name']} ({vendor['id']})",
                done=True,
            )
        except Exception as exc:
            return AgentResult(message=f"Failed to create vendor: {exc}", done=True)

    async def _handle_list(self, entity: str) -> AgentResult:
        try:
            if entity == "customers":
                items = await self._repo.list_customers()
            else:
                items = await self._repo.list_vendors()
            count = len(items)
            names = ", ".join(i.get("name", "?") for i in items[:10])
            extra = f" and {count - 10} more" if count > 10 else ""
            return AgentResult(message=f"{count} {entity}: {names}{extra}", done=True)
        except Exception as exc:
            return AgentResult(message=f"Failed to list {entity}: {exc}", done=True)

    async def _handle_summary(self) -> AgentResult:
        try:
            summary = await self._repo.report_summary()
            lines = "\n".join(f"- {k.replace('_', ' ').title()}: {v}" for k, v in summary.items())
            return AgentResult(message=f"Business Summary:\n{lines}", done=True)
        except Exception as exc:
            return AgentResult(message=f"Failed to get summary: {exc}", done=True)

    # ------------------------------------------------------------------
    # Document dispatch
    # ------------------------------------------------------------------
    @staticmethod
    def _detect_document_type(goal: str) -> str | None:
        if "quotation" in goal or "quote" in goal:
            return "quotation"
        if "invoice" in goal:
            return "invoice"
        if "purchase order" in goal or " po " in goal or goal.startswith("po "):
            return "purchase_order"
        if "boq" in goal or "bill of quantities" in goal:
            return "boq"
        if "estimat" in goal or "material" in goal:
            return "estimation"
        if "report" in goal:
            return "report"
        return None

    def _doc_result(self, doc_type: str, goal: str) -> AgentResult:
        prompt, args = DOC_PROMPTS[doc_type]
        if doc_type in ("quotation", "invoice", "purchase_order"):
            args["sections"][0]["content"] = goal
        if doc_type in ("boq", "estimation"):
            args["rows"] = [["1", goal[:100], "1", "Lot", "TBD", "TBD"]]

        tool_name = (
            "office.create_excel" if doc_type in ("boq", "estimation") else "office.create_word"
        )
        return AgentResult(
            message=prompt,
            tool_call=ToolCallRequest(
                tool_name=tool_name,
                arguments=args,
                rationale=f"Generate {doc_type} document.",
                risk=RiskLevel.SAFE,
            ),
            done=False,
        )
