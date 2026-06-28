from __future__ import annotations

from uuid import uuid4

import pytest

from rabeeh_core.agents.business import BusinessAgent
from rabeeh_core.agents.base import AgentContext
from rabeeh_core.config.schemas import AgentRole


@pytest.fixture
def agent() -> BusinessAgent:
    return BusinessAgent()


@pytest.fixture
def ctx() -> AgentContext:
    return AgentContext(
        task_id=uuid4(),
        session_id=uuid4(),
        goal="test goal",
    )


class TestBusinessAgent:
    def test_role_and_description(self, agent: BusinessAgent) -> None:
        assert agent.role is AgentRole.BUSINESS
        assert agent.description

    def test_system_prompt(self, agent: BusinessAgent) -> None:
        prompt = agent.system_prompt()
        assert "Business Agent" in prompt

    def test_detect_document_type(self, agent: BusinessAgent) -> None:
        assert agent._detect_document_type("create a quotation") == "quotation"
        assert agent._detect_document_type("make a quote") == "quotation"
        assert agent._detect_document_type("generate invoice") == "invoice"
        assert agent._detect_document_type("purchase order for supplies") == "purchase_order"
        assert agent._detect_document_type("create boq for project") == "boq"
        assert agent._detect_document_type("bill of quantities") == "boq"
        assert agent._detect_document_type("estimation for electrical") == "estimation"
        assert agent._detect_document_type("material estimation") == "estimation"
        assert agent._detect_document_type("monthly report") == "report"
        assert agent._detect_document_type("unknown request") is None

    def test_doc_result_quotation(self, agent: BusinessAgent) -> None:
        result = agent._doc_result("quotation", "Office furniture quote")
        assert result.message == "Generate a professional quotation document with the following details."
        assert result.tool_call.tool_name == "office.create_word"
        assert not result.done

    def test_doc_result_invoice(self, agent: BusinessAgent) -> None:
        result = agent._doc_result("invoice", "Consulting invoice")
        assert result.tool_call.tool_name == "office.create_word"

    def test_doc_result_purchase_order(self, agent: BusinessAgent) -> None:
        result = agent._doc_result("purchase_order", "PO for materials")
        assert result.tool_call.tool_name == "office.create_word"

    def test_doc_result_boq(self, agent: BusinessAgent) -> None:
        result = agent._doc_result("boq", "School building BOQ")
        assert result.tool_call.tool_name == "office.create_excel"

    def test_doc_result_estimation(self, agent: BusinessAgent) -> None:
        result = agent._doc_result("estimation", "Electrical estimation")
        assert result.tool_call.tool_name == "office.create_excel"

    def test_doc_result_report(self, agent: BusinessAgent) -> None:
        result = agent._doc_result("report", "Annual report")
        assert result.tool_call.tool_name == "office.create_word"
        assert result.tool_call.risk.value == "safe"

    @pytest.mark.asyncio
    async def test_run_list_customers(self, agent: BusinessAgent, ctx: AgentContext) -> None:
        ctx.goal = "list customers"
        result = await agent.run(ctx)
        assert result.done
        assert "customers" in result.message

    @pytest.mark.asyncio
    async def test_run_summary(self, agent: BusinessAgent, ctx: AgentContext) -> None:
        ctx.goal = "show summary"
        result = await agent.run(ctx)
        assert result.done
        assert "summary" in result.message.lower() or "Business" in result.message

    @pytest.mark.asyncio
    async def test_run_default_document(self, agent: BusinessAgent, ctx: AgentContext) -> None:
        ctx.goal = "generate a contract document"
        result = await agent.run(ctx)
        assert not result.done
        assert result.tool_call is not None

    @pytest.mark.asyncio
    async def test_run_create_customer(self, agent: BusinessAgent, ctx: AgentContext) -> None:
        ctx.goal = "create customer ABC Corp"
        result = await agent.run(ctx)
        assert result.done
        assert "Customer" in result.message

    @pytest.mark.asyncio
    async def test_run_create_vendor(self, agent: BusinessAgent, ctx: AgentContext) -> None:
        ctx.goal = "create vendor Supplier Inc"
        result = await agent.run(ctx)
        assert result.done
        assert "Vendor" in result.message

    @pytest.mark.asyncio
    async def test_run_list_vendors(self, agent: BusinessAgent, ctx: AgentContext) -> None:
        ctx.goal = "list vendors"
        result = await agent.run(ctx)
        assert result.done
        assert "vendors" in result.message
