"""Tests for business domain models, schemas, repository, routes, and agent."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rabeeh_core.api.app import create_app
from rabeeh_core.business.repository import (
    get_business_repository,
    reset_business_repository,
)
from rabeeh_core.business.schemas import (
    BOQCreate,
    CustomerCreate,
    EstimationCreate,
    InvoiceCreate,
    PurchaseOrderCreate,
    QuotationCreate,
    VendorCreate,
)


def _auth_headers(client: TestClient) -> dict[str, str]:
    r = client.post(
        "/auth/login", json={"username": "admin", "password": "dev-only-admin-pw-change-me"}
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_client(app: FastAPI) -> TestClient:
    """A TestClient with a valid auth token already attached."""
    with TestClient(app) as c:
        headers = _auth_headers(c)
        c.headers.update(headers)
        yield c


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_repo():
    reset_business_repository()
    yield


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestSchemas:
    def test_customer_create_valid(self):
        data = CustomerCreate(name="Acme Corp", email="acme@test.com")
        assert data.name == "Acme Corp"
        assert data.email == "acme@test.com"

    def test_customer_create_rejects_extra(self):
        with pytest.raises(ValueError):
            CustomerCreate(name="Test", unknown_field="bad")

    def test_vendor_create(self):
        data = VendorCreate(name="Supplier Inc", payment_terms="Net 30")
        assert data.name == "Supplier Inc"
        assert data.payment_terms == "Net 30"

    def test_quotation_create(self):
        data = QuotationCreate(
            customer_id=uuid4(),
            title="Office Renovation",
            items=[{"description": "Desk", "quantity": 2, "unit_price": 500, "total": 1000}],
        )
        assert data.title == "Office Renovation"
        assert len(data.items) == 1

    def test_invoice_create(self):
        data = InvoiceCreate(
            customer_id=uuid4(),
            items=[{"description": "Service", "quantity": 1, "unit_price": 1000, "total": 1000}],
        )
        assert data.status == "draft"

    def test_purchase_order_create(self):
        data = PurchaseOrderCreate(vendor_id=uuid4())
        assert data.status == "draft"

    def test_boq_create(self):
        data = BOQCreate(
            project_name="School Building",
            items=[
                {
                    "item_code": "A01",
                    "description": "Concrete",
                    "quantity": 100,
                    "unit": "m³",
                    "unit_rate": 120,
                    "amount": 12000,
                }
            ],
        )
        assert data.project_name == "School Building"
        assert data.items[0].unit == "m³"

    def test_estimation_create(self):
        data = EstimationCreate(
            project_name="Electrical Works",
            items=[
                {
                    "description": "Cable",
                    "quantity": 500,
                    "unit": "m",
                    "material_cost_per_unit": 5,
                    "labor_cost_per_unit": 2,
                }
            ],
        )
        assert data.project_name == "Electrical Works"


# ---------------------------------------------------------------------------
# Repository tests (in-memory fallback)
# ---------------------------------------------------------------------------


class TestRepository:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.repo = get_business_repository()

    async def test_customer_crud(self):
        created = await self.repo.create_customer({"name": "Test Customer", "email": "t@t.com"})
        assert created["name"] == "Test Customer"
        cid = created["id"]
        fetched = await self.repo.get_customer(cid)
        assert fetched["name"] == "Test Customer"
        updated = await self.repo.update_customer(cid, {"name": "Updated"})
        assert updated["name"] == "Updated"
        ok = await self.repo.delete_customer(cid)
        assert ok is True
        gone = await self.repo.get_customer(cid)
        assert gone is None

    async def test_customer_list(self):
        await self.repo.create_customer({"name": "A Corp"})
        await self.repo.create_customer({"name": "B Corp"})
        customers = await self.repo.list_customers()
        assert len(customers) >= 2

    async def test_vendor_crud(self):
        created = await self.repo.create_vendor({"name": "Vendor Co", "payment_terms": "Net 30"})
        vid = created["id"]
        fetched = await self.repo.get_vendor(vid)
        assert fetched["payment_terms"] == "Net 30"
        assert await self.repo.delete_vendor(vid) is True

    async def test_quotation_with_items(self):
        cust = await self.repo.create_customer({"name": "Q Customer"})
        data = {
            "customer_id": cust["id"],
            "title": "Test Quote",
            "items": [{"description": "Widget", "quantity": 5, "unit_price": 100, "total": 500}],
        }
        q = await self.repo.create_quotation(data)
        assert q["quote_number"].startswith("Q-")
        assert q["subtotal"] == 500
        assert q["total_amount"] >= 500
        fetched = await self.repo.get_quotation(q["id"])
        assert fetched is not None
        assert len(fetched["items"]) == 1

    async def test_invoice_with_items(self):
        cust = await self.repo.create_customer({"name": "I Customer"})
        data = {
            "customer_id": cust["id"],
            "items": [{"description": "Service", "quantity": 1, "unit_price": 1000, "total": 1000}],
            "tax_rate": 10,
        }
        inv = await self.repo.create_invoice(data)
        assert inv["invoice_number"].startswith("INV-")
        assert inv["subtotal"] == 1000
        assert inv["tax_amount"] == 100
        assert inv["total_amount"] == 1100

    async def test_purchase_order(self):
        vendor = await self.repo.create_vendor({"name": "PO Vendor"})
        data = {
            "vendor_id": vendor["id"],
            "items": [{"description": "Materials", "quantity": 10, "unit_price": 50, "total": 500}],
        }
        po = await self.repo.create_purchase_order(data)
        assert po["po_number"].startswith("PO-")
        assert po["subtotal"] == 500

    async def test_boq(self):
        data = {
            "project_name": "Bridge Construction",
            "items": [
                {
                    "item_code": "B01",
                    "description": "Steel",
                    "quantity": 50,
                    "unit": "ton",
                    "unit_rate": 2000,
                    "amount": 100000,
                }
            ],
        }
        boq = await self.repo.create_boq(data)
        assert boq["boq_number"].startswith("BOQ-")
        assert len(boq["items"]) == 1

    async def test_inventory_crud(self):
        created = await self.repo.create_inventory(
            {
                "item_code": "CBL-001",
                "name": "Cable 4mm",
                "category": "Electrical",
                "quantity": 100,
                "unit_price": 2.5,
                "reorder_level": 20,
            }
        )
        assert created["item_code"] == "CBL-001"
        iid = created["id"]
        fetched = await self.repo.get_inventory(iid)
        assert fetched["name"] == "Cable 4mm"
        updated = await self.repo.update_inventory(iid, {"quantity": 80})
        assert updated["quantity"] == 80
        assert await self.repo.delete_inventory(iid) is True

    async def test_estimation(self):
        data = {
            "project_name": "Office Electrical",
            "items": [
                {
                    "description": "Cable",
                    "quantity": 100,
                    "unit": "m",
                    "material_cost_per_unit": 5,
                    "labor_cost_per_unit": 2,
                },
                {
                    "description": "Switch",
                    "quantity": 20,
                    "unit": "pcs",
                    "material_cost_per_unit": 10,
                    "labor_cost_per_unit": 3,
                },
            ],
        }
        est = await self.repo.create_estimation(data)
        assert est["estimation_number"].startswith("EST-")
        assert est["total_materials_cost"] > 0
        assert est["total_labor_cost"] > 0
        assert est["total_overhead"] > 0
        assert est["grand_total"] > est["total_materials_cost"]

    async def test_report_summary(self):
        await self.repo.create_customer({"name": "R1"})
        await self.repo.create_customer({"name": "R2"})
        summary = await self.repo.report_summary()
        assert summary["customers"] >= 2
        assert "vendors" in summary
        assert "inventory_value" in summary


# ---------------------------------------------------------------------------
# API route tests
# ---------------------------------------------------------------------------


class TestRoutes:
    def test_list_customers_empty(self, auth_client):
        r = auth_client.get("/business/customers")
        assert r.status_code == 200
        assert r.json() == []

    def test_create_customer(self, auth_client):
        r = auth_client.post(
            "/business/customers", json={"name": "API Customer", "email": "api@test.com"}
        )
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "API Customer"
        assert UUID(data["id"])

    def test_create_and_get_customer(self, auth_client):
        created = auth_client.post("/business/customers", json={"name": "Get Test"}).json()
        r = auth_client.get(f"/business/customers/{created['id']}")
        assert r.status_code == 200
        assert r.json()["name"] == "Get Test"

    def test_get_customer_not_found(self, auth_client):
        r = auth_client.get(f"/business/customers/{uuid4()}")
        assert r.status_code == 404

    def test_update_customer(self, auth_client):
        created = auth_client.post("/business/customers", json={"name": "Old Name"}).json()
        r = auth_client.patch(f"/business/customers/{created['id']}", json={"name": "New Name"})
        assert r.status_code == 200
        assert r.json()["name"] == "New Name"

    def test_delete_customer(self, auth_client):
        created = auth_client.post("/business/customers", json={"name": "Delete Me"}).json()
        r = auth_client.delete(f"/business/customers/{created['id']}")
        assert r.status_code == 204
        r2 = auth_client.get(f"/business/customers/{created['id']}")
        assert r2.status_code == 404

    def test_create_vendor(self, auth_client):
        r = auth_client.post("/business/vendors", json={"name": "Vendor Co"})
        assert r.status_code == 201

    def test_create_quotation(self, auth_client):
        cust = auth_client.post("/business/customers", json={"name": "Quote Cust"}).json()
        r = auth_client.post(
            "/business/quotations",
            json={
                "customer_id": cust["id"],
                "title": "Test Quotation",
                "items": [
                    {"description": "Item A", "quantity": 2, "unit_price": 100, "total": 200}
                ],
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["quote_number"].startswith("Q-")

    def test_create_invoice(self, auth_client):
        cust = auth_client.post("/business/customers", json={"name": "Invoice Cust"}).json()
        r = auth_client.post(
            "/business/invoices",
            json={
                "customer_id": cust["id"],
                "items": [
                    {"description": "Service", "quantity": 1, "unit_price": 500, "total": 500}
                ],
            },
        )
        assert r.status_code == 201
        assert r.json()["invoice_number"].startswith("INV-")

    def test_create_purchase_order(self, auth_client):
        vendor = auth_client.post("/business/vendors", json={"name": "PO Vendor"}).json()
        r = auth_client.post(
            "/business/purchase-orders",
            json={
                "vendor_id": vendor["id"],
                "items": [{"description": "Goods", "quantity": 5, "unit_price": 100, "total": 500}],
            },
        )
        assert r.status_code == 201
        assert r.json()["po_number"].startswith("PO-")

    def test_create_boq(self, auth_client):
        r = auth_client.post(
            "/business/boq",
            json={
                "project_name": "Test Project",
                "items": [
                    {
                        "item_code": "A01",
                        "description": "Excavation",
                        "quantity": 100,
                        "unit": "m³",
                        "unit_rate": 50,
                        "amount": 5000,
                    }
                ],
            },
        )
        assert r.status_code == 201
        assert r.json()["boq_number"].startswith("BOQ-")

    def test_create_inventory(self, auth_client):
        r = auth_client.post(
            "/business/inventory",
            json={
                "item_code": "BOLT-001",
                "name": "Bolt M10",
                "category": "Hardware",
                "quantity": 500,
                "unit_price": 0.5,
                "reorder_level": 50,
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["item_code"] == "BOLT-001"
        iid = data["id"]
        r2 = auth_client.get(f"/business/inventory/{iid}")
        assert r2.status_code == 200
        r3 = auth_client.patch(f"/business/inventory/{iid}", json={"quantity": 400})
        assert float(r3.json()["quantity"]) == 400
        r4 = auth_client.delete(f"/business/inventory/{iid}")
        assert r4.status_code == 204

    def test_create_estimation(self, auth_client):
        r = auth_client.post(
            "/business/estimations",
            json={
                "project_name": "Electrical Works",
                "items": [
                    {
                        "description": "Cable 4mm",
                        "quantity": 200,
                        "unit": "m",
                        "material_cost_per_unit": 3,
                        "labor_cost_per_unit": 1.5,
                    },
                ],
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["estimation_number"].startswith("EST-")
        assert float(data["grand_total"]) > 0

    def test_report_summary(self, auth_client):
        r = auth_client.get("/business/reports/summary")
        assert r.status_code == 200
        data = r.json()
        assert "customers" in data
        assert "inventory_value" in data
