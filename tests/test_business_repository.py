"""Business repository CRUD tests — in-memory and DB-backed paths."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest

from rabeeh_core.business.repository import (
    BusinessRepository,
    get_business_repository,
    reset_business_repository,
)


@pytest.fixture(autouse=True)
def _reset_repo() -> None:
    reset_business_repository()


@pytest.fixture()
def repo() -> BusinessRepository:
    return get_business_repository()


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------


class TestCustomers:
    async def test_create_and_get(self, repo: BusinessRepository) -> None:
        c = await repo.create_customer({"name": "Acme Corp", "email": "acme@test.com"})
        assert "id" in c
        assert c["name"] == "Acme Corp"
        fetched = await repo.get_customer(c["id"])
        assert fetched is not None
        assert fetched["name"] == "Acme Corp"

    async def test_get_missing(self, repo: BusinessRepository) -> None:
        assert await repo.get_customer(UUID(int=0)) is None

    async def test_list(self, repo: BusinessRepository) -> None:
        await repo.create_customer({"name": "B"})
        await repo.create_customer({"name": "A"})
        customers = await repo.list_customers()
        assert customers[0]["name"] == "A"
        assert customers[1]["name"] == "B"

    async def test_update(self, repo: BusinessRepository) -> None:
        c = await repo.create_customer({"name": "Old"})
        updated = await repo.update_customer(c["id"], {"name": "New"})
        assert updated is not None
        assert updated["name"] == "New"

    async def test_update_missing(self, repo: BusinessRepository) -> None:
        assert await repo.update_customer(UUID(int=0), {"name": "x"}) is None

    async def test_delete(self, repo: BusinessRepository) -> None:
        c = await repo.create_customer({"name": "Del"})
        assert await repo.delete_customer(c["id"]) is True
        assert await repo.get_customer(c["id"]) is None

    async def test_delete_missing(self, repo: BusinessRepository) -> None:
        assert await repo.delete_customer(UUID(int=0)) is False


# ---------------------------------------------------------------------------
# Vendors
# ---------------------------------------------------------------------------


class TestVendors:
    async def test_create_and_get(self, repo: BusinessRepository) -> None:
        v = await repo.create_vendor({"name": "Supplier Inc", "email": "supplier@test.com"})
        assert v["name"] == "Supplier Inc"
        fetched = await repo.get_vendor(v["id"])
        assert fetched is not None

    async def test_get_missing(self, repo: BusinessRepository) -> None:
        assert await repo.get_vendor(UUID(int=0)) is None

    async def test_list(self, repo: BusinessRepository) -> None:
        await repo.create_vendor({"name": "Z"})
        await repo.create_vendor({"name": "A"})
        vendors = await repo.list_vendors()
        assert vendors[0]["name"] == "A"

    async def test_update(self, repo: BusinessRepository) -> None:
        v = await repo.create_vendor({"name": "Old Vendor"})
        updated = await repo.update_vendor(v["id"], {"name": "New Vendor"})
        assert updated["name"] == "New Vendor"

    async def test_update_missing(self, repo: BusinessRepository) -> None:
        assert await repo.update_vendor(UUID(int=0), {"name": "x"}) is None

    async def test_delete(self, repo: BusinessRepository) -> None:
        v = await repo.create_vendor({"name": "Del Vendor"})
        assert await repo.delete_vendor(v["id"]) is True
        assert await repo.get_vendor(v["id"]) is None

    async def test_delete_missing(self, repo: BusinessRepository) -> None:
        assert await repo.delete_vendor(UUID(int=0)) is False


# ---------------------------------------------------------------------------
# Quotations
# ---------------------------------------------------------------------------


class TestQuotations:
    async def test_create_with_items(self, repo: BusinessRepository) -> None:
        q = await repo.create_quotation(
            {
                "customer_id": UUID(int=1),
                "title": "Quote 1",
                "items": [
                    {
                        "description": "Item A",
                        "quantity": 2,
                        "unit_price": "50.00",
                        "total": "100.00",
                    },
                ],
            }
        )
        assert "id" in q
        assert q["quote_number"].startswith("Q-")
        assert q["total_amount"] == Decimal("100.00")
        assert q["status"] == "draft"
        assert len(q.get("items", [])) == 1

    async def test_create_empty_items(self, repo: BusinessRepository) -> None:
        q = await repo.create_quotation(
            {
                "customer_id": UUID(int=1),
                "title": "Empty Quote",
            }
        )
        assert q["total_amount"] == Decimal("0.00")

    async def test_create_with_tax(self, repo: BusinessRepository) -> None:
        q = await repo.create_quotation(
            {
                "customer_id": UUID(int=1),
                "title": "Taxed Quote",
                "tax_rate": "15.00",
                "items": [
                    {
                        "description": "Item",
                        "quantity": 1,
                        "unit_price": "100.00",
                        "total": "100.00",
                    },
                ],
            }
        )
        assert q["tax_amount"] == Decimal("15.00")
        assert q["total_amount"] == Decimal("115.00")

    async def test_get_missing(self, repo: BusinessRepository) -> None:
        assert await repo.get_quotation(UUID(int=0)) is None

    async def test_list(self, repo: BusinessRepository) -> None:
        await repo.create_quotation({"customer_id": UUID(int=1), "title": "Q1"})
        assert len(await repo.list_quotations()) == 1

    async def test_get_with_items(self, repo: BusinessRepository) -> None:
        q = await repo.create_quotation(
            {
                "customer_id": UUID(int=1),
                "title": "Q With Items",
                "items": [
                    {"description": "Test", "quantity": 1, "unit_price": "10.00", "total": "10.00"}
                ],
            }
        )
        fetched = await repo.get_quotation(q["id"])
        assert fetched is not None
        assert len(fetched.get("items", [])) == 1


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------


class TestInvoices:
    async def test_create_with_items(self, repo: BusinessRepository) -> None:
        inv = await repo.create_invoice(
            {
                "customer_id": UUID(int=1),
                "items": [
                    {
                        "description": "Service",
                        "quantity": 1,
                        "unit_price": "200.00",
                        "total": "200.00",
                    }
                ],
            }
        )
        assert inv["invoice_number"].startswith("INV-")
        assert inv["total_amount"] == Decimal("200.00")

    async def test_create_empty_items(self, repo: BusinessRepository) -> None:
        inv = await repo.create_invoice({"customer_id": UUID(int=1)})
        assert inv["total_amount"] == Decimal("0.00")

    async def test_get_missing(self, repo: BusinessRepository) -> None:
        assert await repo.get_invoice(UUID(int=0)) is None

    async def test_list(self, repo: BusinessRepository) -> None:
        await repo.create_invoice({"customer_id": UUID(int=1)})
        assert len(await repo.list_invoices()) == 1

    async def test_get_with_items(self, repo: BusinessRepository) -> None:
        inv = await repo.create_invoice(
            {
                "customer_id": UUID(int=1),
                "items": [
                    {"description": "Item", "quantity": 2, "unit_price": "15.00", "total": "30.00"}
                ],
            }
        )
        fetched = await repo.get_invoice(inv["id"])
        assert fetched is not None
        assert len(fetched.get("items", [])) == 1


# ---------------------------------------------------------------------------
# Purchase Orders
# ---------------------------------------------------------------------------


class TestPurchaseOrders:
    async def test_create_with_items(self, repo: BusinessRepository) -> None:
        po = await repo.create_purchase_order(
            {
                "vendor_id": UUID(int=1),
                "items": [
                    {
                        "description": "Part X",
                        "quantity": 10,
                        "unit_price": "5.00",
                        "total": "50.00",
                    }
                ],
            }
        )
        assert po["po_number"].startswith("PO-")
        assert po["total_amount"] == Decimal("50.00")

    async def test_create_empty_items(self, repo: BusinessRepository) -> None:
        po = await repo.create_purchase_order({"vendor_id": UUID(int=1)})
        assert po["total_amount"] == Decimal("0.00")

    async def test_get_missing(self, repo: BusinessRepository) -> None:
        assert await repo.get_purchase_order(UUID(int=0)) is None

    async def test_list(self, repo: BusinessRepository) -> None:
        await repo.create_purchase_order({"vendor_id": UUID(int=1)})
        assert len(await repo.list_purchase_orders()) == 1

    async def test_get_with_items(self, repo: BusinessRepository) -> None:
        po = await repo.create_purchase_order(
            {
                "vendor_id": UUID(int=1),
                "items": [
                    {"description": "Item", "quantity": 3, "unit_price": "20.00", "total": "60.00"}
                ],
            }
        )
        fetched = await repo.get_purchase_order(po["id"])
        assert fetched is not None
        assert len(fetched.get("items", [])) == 1


# ---------------------------------------------------------------------------
# BOQ
# ---------------------------------------------------------------------------


class TestBOQ:
    async def test_create_with_items(self, repo: BusinessRepository) -> None:
        boq = await repo.create_boq(
            {
                "project_name": "Project Alpha",
                "items": [
                    {
                        "item_code": "C001",
                        "description": "Cable",
                        "quantity": 100,
                        "unit_rate": "2.50",
                        "amount": "250.00",
                    }
                ],
            }
        )
        assert boq["boq_number"].startswith("BOQ-")
        assert boq["project_name"] == "Project Alpha"
        assert len(boq.get("items", [])) == 1

    async def test_get_missing(self, repo: BusinessRepository) -> None:
        assert await repo.get_boq(UUID(int=0)) is None

    async def test_list(self, repo: BusinessRepository) -> None:
        await repo.create_boq({"project_name": "P1"})
        assert len(await repo.list_boqs()) == 1

    async def test_default_status(self, repo: BusinessRepository) -> None:
        boq = await repo.create_boq({"project_name": "P1"})
        assert boq["status"] == "draft"


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


class TestInventory:
    async def test_create_and_get(self, repo: BusinessRepository) -> None:
        item = await repo.create_inventory(
            {"item_code": "INV001", "name": "Widget", "quantity": 100, "unit_price": "9.99"}
        )
        assert item["item_code"] == "INV001"
        fetched = await repo.get_inventory(item["id"])
        assert fetched is not None

    async def test_get_missing(self, repo: BusinessRepository) -> None:
        assert await repo.get_inventory(UUID(int=0)) is None

    async def test_list(self, repo: BusinessRepository) -> None:
        await repo.create_inventory({"item_code": "B", "name": "B"})
        await repo.create_inventory({"item_code": "A", "name": "A"})
        items = await repo.list_inventory()
        assert items[0]["name"] == "A"

    async def test_update(self, repo: BusinessRepository) -> None:
        item = await repo.create_inventory({"item_code": "UPD", "name": "Old", "quantity": 10})
        updated = await repo.update_inventory(item["id"], {"name": "New"})
        assert updated["name"] == "New"

    async def test_update_missing(self, repo: BusinessRepository) -> None:
        assert await repo.update_inventory(UUID(int=0), {"name": "x"}) is None

    async def test_delete(self, repo: BusinessRepository) -> None:
        item = await repo.create_inventory({"item_code": "DEL", "name": "Del", "quantity": 0})
        assert await repo.delete_inventory(item["id"]) is True
        assert await repo.get_inventory(item["id"]) is None

    async def test_delete_missing(self, repo: BusinessRepository) -> None:
        assert await repo.delete_inventory(UUID(int=0)) is False

    async def test_default_unit(self, repo: BusinessRepository) -> None:
        item = await repo.create_inventory({"item_code": "UNIT", "name": "U", "quantity": 1})
        assert item["unit"] == "Each"


# ---------------------------------------------------------------------------
# Estimations
# ---------------------------------------------------------------------------


class TestEstimations:
    async def test_create_with_items(self, repo: BusinessRepository) -> None:
        est = await repo.create_estimation(
            {
                "project_name": "Electrical Project",
                "items": [
                    {
                        "item_code": "E001",
                        "description": "Wiring",
                        "quantity": 50,
                        "material_cost_per_unit": "10.00",
                        "labor_cost_per_unit": "5.00",
                    },
                ],
            }
        )
        assert est["estimation_number"].startswith("EST-")
        # material: 50*10 = 500, labor: 50*5 = 250, overhead: (500+250)*0.1 = 75, grand: 825
        assert est["total_materials_cost"] == Decimal("500.00")
        assert est["total_labor_cost"] == Decimal("250.00")
        assert est["total_overhead"] == Decimal("75.00")
        assert est["grand_total"] == Decimal("825.00")
        assert len(est.get("items", [])) == 1

    async def test_create_empty_items(self, repo: BusinessRepository) -> None:
        est = await repo.create_estimation({"project_name": "Empty Est"})
        assert est["grand_total"] == Decimal("0.00")

    async def test_get_missing(self, repo: BusinessRepository) -> None:
        assert await repo.get_estimation(UUID(int=0)) is None

    async def test_list(self, repo: BusinessRepository) -> None:
        await repo.create_estimation({"project_name": "P1"})
        assert len(await repo.list_estimations()) == 1

    async def test_default_status(self, repo: BusinessRepository) -> None:
        est = await repo.create_estimation({"project_name": "P1"})
        assert est["status"] == "draft"


# ---------------------------------------------------------------------------
# Report summary
# ---------------------------------------------------------------------------


class TestReports:
    async def test_report_summary_empty(self, repo: BusinessRepository) -> None:
        summary = await repo.report_summary()
        assert summary["customers"] == 0
        assert summary["vendors"] == 0
        assert summary["quotations"] == 0

    async def test_report_summary_with_data(self, repo: BusinessRepository) -> None:
        await repo.create_customer({"name": "C1"})
        await repo.create_vendor({"name": "V1"})
        await repo.create_inventory(
            {"item_code": "I1", "name": "Inv1", "quantity": 10, "unit_price": "5.00"}
        )
        summary = await repo.report_summary()
        assert summary["customers"] == 1
        assert summary["vendors"] == 1
        assert summary["inventory_items"] == 1


# ---------------------------------------------------------------------------
# Decimal precision / numeric field edge cases
# ---------------------------------------------------------------------------


class TestDecimalPrecision:
    async def test_quotation_tax_rounding(self, repo: BusinessRepository) -> None:
        q = await repo.create_quotation(
            {
                "customer_id": UUID(int=1),
                "title": "Rounding",
                "tax_rate": "8.5",
                "items": [
                    {"description": "Item", "quantity": 3, "unit_price": "1.33", "total": "3.99"}
                ],
            }
        )
        assert q["tax_amount"] == Decimal("0.34")

    async def test_zero_quantity_items(self, repo: BusinessRepository) -> None:
        q = await repo.create_quotation(
            {
                "customer_id": UUID(int=1),
                "title": "Zero Qty",
                "items": [
                    {"description": "Free", "quantity": 0, "unit_price": "0.00", "total": "0.00"}
                ],
            }
        )
        assert q["total_amount"] == Decimal("0.00")

    async def test_large_values(self, repo: BusinessRepository) -> None:
        inv = await repo.create_invoice(
            {
                "customer_id": UUID(int=1),
                "items": [
                    {
                        "description": "Big",
                        "quantity": 1000000,
                        "unit_price": "999.99",
                        "total": "999990000.00",
                    }
                ],
            }
        )
        assert inv["total_amount"] > 0


# ---------------------------------------------------------------------------
# DB-backed tests (use sqlite_db fixture to exercise SQLAlchemy path)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("sqlite_db")
class TestDbBacked:
    """Run CRUD against the real async SQLite engine via sqlite_db fixture."""

    async def _repo(self) -> BusinessRepository:
        reset_business_repository()
        return get_business_repository()

    async def test_create_and_get_customer(self) -> None:
        repo = await self._repo()
        c = await repo.create_customer({"name": "DB Customer", "email": "db@test.com"})
        assert "id" in c
        fetched = await repo.get_customer(c["id"])
        assert fetched is not None
        assert fetched["name"] == "DB Customer"

    async def test_list_customers(self) -> None:
        repo = await self._repo()
        await repo.create_customer({"name": "B"})
        await repo.create_customer({"name": "A"})
        customers = await repo.list_customers()
        assert len(customers) == 2

    async def test_update_customer(self) -> None:
        repo = await self._repo()
        c = await repo.create_customer({"name": "Old"})
        updated = await repo.update_customer(c["id"], {"name": "New"})
        assert updated["name"] == "New"

    async def test_delete_customer(self) -> None:
        repo = await self._repo()
        c = await repo.create_customer({"name": "Del"})
        assert await repo.delete_customer(c["id"]) is True
        assert await repo.get_customer(c["id"]) is None

    async def test_create_vendor(self) -> None:
        repo = await self._repo()
        v = await repo.create_vendor({"name": "DB Vendor", "email": "v@test.com"})
        fetched = await repo.get_vendor(v["id"])
        assert fetched["name"] == "DB Vendor"

    async def test_list_vendors(self) -> None:
        repo = await self._repo()
        await repo.create_vendor({"name": "Z"})
        await repo.create_vendor({"name": "A"})
        vendors = await repo.list_vendors()
        assert len(vendors) == 2

    async def test_create_quotation_with_items(self) -> None:
        repo = await self._repo()
        q = await repo.create_quotation(
            {
                "customer_id": UUID(int=1),
                "title": "DB Quote",
                "items": [
                    {"description": "Item", "quantity": 2, "unit_price": "50.00", "total": "100.00"}
                ],
            }
        )
        assert q["total_amount"] == Decimal("100.00")
        assert len(q.get("items", [])) == 1

    async def test_get_quotation_with_items(self) -> None:
        repo = await self._repo()
        q = await repo.create_quotation(
            {
                "customer_id": UUID(int=1),
                "title": "DB Quote",
                "items": [
                    {
                        "description": "Item X",
                        "quantity": 1,
                        "unit_price": "10.00",
                        "total": "10.00",
                    }
                ],
            }
        )
        fetched = await repo.get_quotation(q["id"])
        assert fetched is not None
        assert len(fetched.get("items", [])) == 1
        assert fetched["items"][0]["description"] == "Item X"

    async def test_create_invoice(self) -> None:
        repo = await self._repo()
        inv = await repo.create_invoice(
            {
                "customer_id": UUID(int=1),
                "items": [
                    {
                        "description": "Service",
                        "quantity": 1,
                        "unit_price": "200.00",
                        "total": "200.00",
                    }
                ],
            }
        )
        assert inv["invoice_number"].startswith("INV-")

    async def test_list_invoices(self) -> None:
        repo = await self._repo()
        await repo.create_invoice({"customer_id": UUID(int=1)})
        assert len(await repo.list_invoices()) == 1

    async def test_create_purchase_order(self) -> None:
        repo = await self._repo()
        po = await repo.create_purchase_order(
            {
                "vendor_id": UUID(int=1),
                "items": [
                    {"description": "Part", "quantity": 10, "unit_price": "5.00", "total": "50.00"}
                ],
            }
        )
        assert po["po_number"].startswith("PO-")

    async def test_get_purchase_order_with_items(self) -> None:
        repo = await self._repo()
        po = await repo.create_purchase_order(
            {
                "vendor_id": UUID(int=1),
                "items": [
                    {
                        "description": "Part A",
                        "quantity": 5,
                        "unit_price": "20.00",
                        "total": "100.00",
                    }
                ],
            }
        )
        fetched = await repo.get_purchase_order(po["id"])
        assert fetched is not None
        assert len(fetched.get("items", [])) == 1

    async def test_list_purchase_orders(self) -> None:
        repo = await self._repo()
        await repo.create_purchase_order({"vendor_id": UUID(int=1)})
        await repo.create_purchase_order({"vendor_id": UUID(int=2)})
        assert len(await repo.list_purchase_orders()) == 2

    async def test_create_boq(self) -> None:
        repo = await self._repo()
        boq = await repo.create_boq(
            {
                "project_name": "DB Project",
                "items": [
                    {
                        "item_code": "C001",
                        "description": "Cable",
                        "quantity": 100,
                        "unit_rate": "2.50",
                        "amount": "250.00",
                    }
                ],
            }
        )
        assert boq["boq_number"].startswith("BOQ-")
        assert boq["project_name"] == "DB Project"

    async def test_get_boq_with_items(self) -> None:
        repo = await self._repo()
        boq = await repo.create_boq(
            {
                "project_name": "P1",
                "items": [
                    {
                        "item_code": "W001",
                        "description": "Wire",
                        "quantity": 50,
                        "unit_rate": "1.00",
                        "amount": "50.00",
                    }
                ],
            }
        )
        fetched = await repo.get_boq(boq["id"])
        assert fetched is not None
        assert len(fetched.get("items", [])) == 1

    async def test_list_boqs(self) -> None:
        repo = await self._repo()
        await repo.create_boq({"project_name": "P1"})
        await repo.create_boq({"project_name": "P2"})
        assert len(await repo.list_boqs()) == 2

    async def test_create_inventory_item(self) -> None:
        repo = await self._repo()
        item = await repo.create_inventory(
            {"item_code": "DB001", "name": "DB Item", "quantity": 50}
        )
        fetched = await repo.get_inventory(item["id"])
        assert fetched["item_code"] == "DB001"

    async def test_update_inventory_item(self) -> None:
        repo = await self._repo()
        item = await repo.create_inventory({"item_code": "UPD", "name": "Old", "quantity": 10})
        updated = await repo.update_inventory(item["id"], {"name": "New", "quantity": 20})
        assert updated["name"] == "New"
        assert updated["quantity"] == 20

    async def test_delete_inventory_item(self) -> None:
        repo = await self._repo()
        item = await repo.create_inventory({"item_code": "DEL", "name": "Del", "quantity": 0})
        assert await repo.delete_inventory(item["id"]) is True
        assert await repo.get_inventory(item["id"]) is None

    async def test_list_inventory(self) -> None:
        repo = await self._repo()
        await repo.create_inventory({"item_code": "B", "name": "B"})
        await repo.create_inventory({"item_code": "A", "name": "A"})
        assert len(await repo.list_inventory()) == 2

    async def test_create_estimation(self) -> None:
        repo = await self._repo()
        est = await repo.create_estimation(
            {
                "project_name": "DB Est",
                "items": [
                    {
                        "item_code": "E001",
                        "description": "Labor",
                        "quantity": 10,
                        "material_cost_per_unit": "100.00",
                        "labor_cost_per_unit": "50.00",
                    }
                ],
            }
        )
        assert est["estimation_number"].startswith("EST-")
        # materials: 10*100=1000, labor: 10*50=500, overhead: (1000+500)*0.1=150, grand: 1650
        assert est["grand_total"] == Decimal("1650.00")

    async def test_get_estimation_with_items(self) -> None:
        repo = await self._repo()
        est = await repo.create_estimation(
            {
                "project_name": "P1",
                "items": [
                    {
                        "item_code": "E001",
                        "description": "Work",
                        "quantity": 5,
                        "material_cost_per_unit": "20.00",
                        "labor_cost_per_unit": "10.00",
                    }
                ],
            }
        )
        fetched = await repo.get_estimation(est["id"])
        assert fetched is not None
        assert len(fetched.get("items", [])) == 1

    async def test_list_estimations(self) -> None:
        repo = await self._repo()
        await repo.create_estimation({"project_name": "P1"})
        await repo.create_estimation({"project_name": "P2"})
        assert len(await repo.list_estimations()) == 2

    async def test_report_summary(self) -> None:
        repo = await self._repo()
        await repo.create_customer({"name": "C1"})
        await repo.create_vendor({"name": "V1"})
        await repo.create_inventory(
            {"item_code": "I1", "name": "Inv1", "quantity": 10, "unit_price": "5.00"}
        )
        await repo.create_invoice(
            {
                "customer_id": UUID(int=1),
                "status": "sent",
                "items": [
                    {"description": "Svc", "quantity": 1, "unit_price": "100.00", "total": "100.00"}
                ],
            }
        )
        summary = await repo.report_summary()
        assert summary["customers"] >= 1
        assert summary["vendors"] >= 1
        assert summary["inventory_items"] >= 1
