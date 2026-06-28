from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..persistence.db import db_available, get_session_factory
from .models import (
    BOQ,
    BOQItem,
    Customer,
    ElectricalEstimation,
    EstimationItem,
    InventoryItem,
    Invoice,
    InvoiceItem,
    PurchaseOrder,
    PurchaseOrderItem,
    Quotation,
    QuotationItem,
    Vendor,
)

_log = logging.getLogger(__name__)


def _next_number(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8].upper()}"


class BusinessRepository:
    """Persist + retrieve business entities with in-memory fallback."""

    def __init__(self) -> None:
        self._customers: dict[str, dict[str, Any]] = {}
        self._vendors: dict[str, dict[str, Any]] = {}
        self._quotations: dict[str, dict[str, Any]] = {}
        self._invoices: dict[str, dict[str, Any]] = {}
        self._pos: dict[str, dict[str, Any]] = {}
        self._boqs: dict[str, dict[str, Any]] = {}
        self._inventory: dict[str, dict[str, Any]] = {}
        self._estimations: dict[str, dict[str, Any]] = {}

    async def _session(self) -> AsyncSession | None:
        if not db_available():
            return None
        return get_session_factory()()

    @staticmethod
    def _to_dict(obj: Any) -> dict[str, Any]:
        return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}

    # ------------------------------------------------------------------
    # Customers
    # ------------------------------------------------------------------
    async def create_customer(self, data: dict[str, Any]) -> dict[str, Any]:
        sess = await self._session()
        if sess is None:
            row = data | {
                "id": uuid4(),
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
            self._customers[str(row["id"])] = row
            return row
        async with sess:
            db_row = Customer(id=uuid4(), **data)
            sess.add(db_row)
            await sess.commit()
            await sess.refresh(db_row)
            return self._to_dict(db_row)

    async def get_customer(self, customer_id: UUID) -> dict[str, Any] | None:
        sess = await self._session()
        if sess is None:
            return self._customers.get(str(customer_id))
        async with sess:
            row = await sess.get(Customer, customer_id)
            return self._to_dict(row) if row else None

    async def list_customers(self) -> list[dict[str, Any]]:
        sess = await self._session()
        if sess is None:
            return sorted(self._customers.values(), key=lambda x: x.get("name", ""))
        async with sess:
            rows = (await sess.execute(select(Customer).order_by(Customer.name))).scalars().all()
            return [self._to_dict(r) for r in rows]

    async def update_customer(
        self, customer_id: UUID, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        sess = await self._session()
        if sess is None:
            cid = str(customer_id)
            if cid not in self._customers:
                return None
            self._customers[cid].update(data)
            self._customers[cid]["updated_at"] = datetime.now(UTC)
            return self._customers[cid]
        async with sess:
            row = await sess.get(Customer, customer_id)
            if not row:
                return None
            for k, v in data.items():
                if v is not None:
                    setattr(row, k, v)
            row.updated_at = datetime.now(UTC)
            await sess.commit()
            await sess.refresh(row)
            return self._to_dict(row)

    async def delete_customer(self, customer_id: UUID) -> bool:
        sess = await self._session()
        if sess is None:
            return bool(self._customers.pop(str(customer_id), None))
        async with sess:
            row = await sess.get(Customer, customer_id)
            if not row:
                return False
            await sess.delete(row)
            await sess.commit()
            return True

    # ------------------------------------------------------------------
    # Vendors
    # ------------------------------------------------------------------
    async def create_vendor(self, data: dict[str, Any]) -> dict[str, Any]:
        sess = await self._session()
        if sess is None:
            row = data | {
                "id": uuid4(),
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
            self._vendors[str(row["id"])] = row
            return row
        async with sess:
            db_row = Vendor(id=uuid4(), **data)
            sess.add(db_row)
            await sess.commit()
            await sess.refresh(db_row)
            return self._to_dict(db_row)

    async def get_vendor(self, vendor_id: UUID) -> dict[str, Any] | None:
        sess = await self._session()
        if sess is None:
            return self._vendors.get(str(vendor_id))
        async with sess:
            row = await sess.get(Vendor, vendor_id)
            return self._to_dict(row) if row else None

    async def list_vendors(self) -> list[dict[str, Any]]:
        sess = await self._session()
        if sess is None:
            return sorted(self._vendors.values(), key=lambda x: x.get("name", ""))
        async with sess:
            rows = (await sess.execute(select(Vendor).order_by(Vendor.name))).scalars().all()
            return [self._to_dict(r) for r in rows]

    async def update_vendor(self, vendor_id: UUID, data: dict[str, Any]) -> dict[str, Any] | None:
        sess = await self._session()
        if sess is None:
            vid = str(vendor_id)
            if vid not in self._vendors:
                return None
            self._vendors[vid].update(data)
            self._vendors[vid]["updated_at"] = datetime.now(UTC)
            return self._vendors[vid]
        async with sess:
            row = await sess.get(Vendor, vendor_id)
            if not row:
                return None
            for k, v in data.items():
                if v is not None:
                    setattr(row, k, v)
            row.updated_at = datetime.now(UTC)
            await sess.commit()
            await sess.refresh(row)
            return self._to_dict(row)

    async def delete_vendor(self, vendor_id: UUID) -> bool:
        sess = await self._session()
        if sess is None:
            return bool(self._vendors.pop(str(vendor_id), None))
        async with sess:
            row = await sess.get(Vendor, vendor_id)
            if not row:
                return False
            await sess.delete(row)
            await sess.commit()
            return True

    # ------------------------------------------------------------------
    # Quotations
    # ------------------------------------------------------------------
    async def create_quotation(self, data: dict[str, Any]) -> dict[str, Any]:
        items_data = data.pop("items", [])
        data["quote_number"] = _next_number("Q")
        subtotal = sum(Decimal(str(i.get("total", 0))) for i in items_data)
        data["subtotal"] = subtotal
        tax_rate = Decimal(str(data.get("tax_rate", 0)))
        data["tax_amount"] = (subtotal * tax_rate / Decimal("100")).quantize(Decimal("0.01"))
        data["total_amount"] = subtotal + data["tax_amount"]

        sess = await self._session()
        defaults = {"status": "draft", "tax_rate": Decimal("0.00")}
        for k, v in defaults.items():
            data.setdefault(k, v)
        if sess is None:
            row = data | {
                "id": uuid4(),
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "items": items_data,
            }
            self._quotations[str(row["id"])] = row
            return row
        async with sess:
            db_row = Quotation(id=uuid4(), **data)
            sess.add(db_row)
            for item in items_data:
                sess.add(QuotationItem(quotation_id=db_row.id, **item))
            await sess.commit()
            await sess.refresh(db_row)
            return await self._quotation_to_dict(sess, db_row)

    async def get_quotation(self, quotation_id: UUID) -> dict[str, Any] | None:
        sess = await self._session()
        if sess is None:
            return self._quotations.get(str(quotation_id))
        async with sess:
            row = await sess.get(Quotation, quotation_id)
            return await self._quotation_to_dict(sess, row) if row else None

    async def list_quotations(self) -> list[dict[str, Any]]:
        sess = await self._session()
        if sess is None:
            return sorted(
                self._quotations.values(), key=lambda x: x.get("created_at", ""), reverse=True
            )
        async with sess:
            rows = (
                (await sess.execute(select(Quotation).order_by(Quotation.created_at.desc())))
                .scalars()
                .all()
            )
            return [await self._quotation_to_dict(sess, r) for r in rows]

    async def _quotation_to_dict(self, sess: AsyncSession, r: Quotation) -> dict[str, Any]:
        await sess.refresh(r, ["items"])
        d = self._to_dict(r)
        d["items"] = [self._to_dict(i) for i in r.items]
        return d

    # ------------------------------------------------------------------
    # Invoices
    # ------------------------------------------------------------------
    async def create_invoice(self, data: dict[str, Any]) -> dict[str, Any]:
        items_data = data.pop("items", [])
        data["invoice_number"] = _next_number("INV")
        subtotal = sum(Decimal(str(i.get("total", 0))) for i in items_data)
        data["subtotal"] = subtotal
        tax_rate = Decimal(str(data.get("tax_rate", 0)))
        data["tax_amount"] = (subtotal * tax_rate / Decimal("100")).quantize(Decimal("0.01"))
        data["total_amount"] = subtotal + data["tax_amount"]

        sess = await self._session()
        defaults = {"status": "draft", "tax_rate": Decimal("0.00")}
        for k, v in defaults.items():
            data.setdefault(k, v)
        if sess is None:
            row = data | {
                "id": uuid4(),
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "items": items_data,
            }
            self._invoices[str(row["id"])] = row
            return row
        async with sess:
            db_row = Invoice(id=uuid4(), **data)
            sess.add(db_row)
            for item in items_data:
                sess.add(InvoiceItem(invoice_id=db_row.id, **item))
            await sess.commit()
            await sess.refresh(db_row)
            return await self._invoice_to_dict(sess, db_row)

    async def get_invoice(self, invoice_id: UUID) -> dict[str, Any] | None:
        sess = await self._session()
        if sess is None:
            return self._invoices.get(str(invoice_id))
        async with sess:
            row = await sess.get(Invoice, invoice_id)
            return await self._invoice_to_dict(sess, row) if row else None

    async def list_invoices(self) -> list[dict[str, Any]]:
        sess = await self._session()
        if sess is None:
            return sorted(
                self._invoices.values(), key=lambda x: x.get("created_at", ""), reverse=True
            )
        async with sess:
            rows = (
                (await sess.execute(select(Invoice).order_by(Invoice.created_at.desc())))
                .scalars()
                .all()
            )
            return [await self._invoice_to_dict(sess, r) for r in rows]

    async def _invoice_to_dict(self, sess: AsyncSession, r: Invoice) -> dict[str, Any]:
        await sess.refresh(r, ["items"])
        d = self._to_dict(r)
        d["items"] = [self._to_dict(i) for i in r.items]
        return d

    # ------------------------------------------------------------------
    # Purchase Orders
    # ------------------------------------------------------------------
    async def create_purchase_order(self, data: dict[str, Any]) -> dict[str, Any]:
        items_data = data.pop("items", [])
        data["po_number"] = _next_number("PO")
        subtotal = sum(Decimal(str(i.get("total", 0))) for i in items_data)
        data["subtotal"] = subtotal
        tax_rate = Decimal(str(data.get("tax_rate", 0)))
        data["tax_amount"] = (subtotal * tax_rate / Decimal("100")).quantize(Decimal("0.01"))
        data["total_amount"] = subtotal + data["tax_amount"]

        sess = await self._session()
        defaults = {"status": "draft", "tax_rate": Decimal("0.00")}
        for k, v in defaults.items():
            data.setdefault(k, v)
        if sess is None:
            row = data | {
                "id": uuid4(),
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "items": items_data,
            }
            self._pos[str(row["id"])] = row
            return row
        async with sess:
            db_row = PurchaseOrder(id=uuid4(), **data)
            sess.add(db_row)
            for item in items_data:
                sess.add(PurchaseOrderItem(po_id=db_row.id, **item))
            await sess.commit()
            await sess.refresh(db_row)
            return await self._po_to_dict(sess, db_row)

    async def get_purchase_order(self, po_id: UUID) -> dict[str, Any] | None:
        sess = await self._session()
        if sess is None:
            return self._pos.get(str(po_id))
        async with sess:
            row = await sess.get(PurchaseOrder, po_id)
            return await self._po_to_dict(sess, row) if row else None

    async def list_purchase_orders(self) -> list[dict[str, Any]]:
        sess = await self._session()
        if sess is None:
            return sorted(self._pos.values(), key=lambda x: x.get("created_at", ""), reverse=True)
        async with sess:
            rows = (
                (
                    await sess.execute(
                        select(PurchaseOrder).order_by(PurchaseOrder.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            return [await self._po_to_dict(sess, r) for r in rows]

    async def _po_to_dict(self, sess: AsyncSession, r: PurchaseOrder) -> dict[str, Any]:
        await sess.refresh(r, ["items"])
        d = self._to_dict(r)
        d["items"] = [self._to_dict(i) for i in r.items]
        return d

    # ------------------------------------------------------------------
    # BOQ
    # ------------------------------------------------------------------
    async def create_boq(self, data: dict[str, Any]) -> dict[str, Any]:
        items_data = data.pop("items", [])
        data["boq_number"] = _next_number("BOQ")

        sess = await self._session()
        data.setdefault("status", "draft")
        if sess is None:
            row = data | {
                "id": uuid4(),
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "items": items_data,
            }
            self._boqs[str(row["id"])] = row
            return row
        async with sess:
            db_row = BOQ(id=uuid4(), **data)
            sess.add(db_row)
            for item in items_data:
                sess.add(BOQItem(boq_id=db_row.id, **item))
            await sess.commit()
            await sess.refresh(db_row)
            return await self._boq_to_dict(sess, db_row)

    async def get_boq(self, boq_id: UUID) -> dict[str, Any] | None:
        sess = await self._session()
        if sess is None:
            return self._boqs.get(str(boq_id))
        async with sess:
            row = await sess.get(BOQ, boq_id)
            return await self._boq_to_dict(sess, row) if row else None

    async def list_boqs(self) -> list[dict[str, Any]]:
        sess = await self._session()
        if sess is None:
            return sorted(self._boqs.values(), key=lambda x: x.get("created_at", ""), reverse=True)
        async with sess:
            rows = (await sess.execute(select(BOQ).order_by(BOQ.created_at.desc()))).scalars().all()
            return [await self._boq_to_dict(sess, r) for r in rows]

    async def _boq_to_dict(self, sess: AsyncSession, r: BOQ) -> dict[str, Any]:
        await sess.refresh(r, ["items"])
        d = self._to_dict(r)
        d["items"] = [self._to_dict(i) for i in r.items]
        return d

    # ------------------------------------------------------------------
    # Inventory
    # ------------------------------------------------------------------
    async def create_inventory(self, data: dict[str, Any]) -> dict[str, Any]:
        sess = await self._session()
        data.setdefault("unit", "Each")
        if sess is None:
            row = data | {
                "id": uuid4(),
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
            self._inventory[str(row["id"])] = row
            return row
        async with sess:
            db_row = InventoryItem(id=uuid4(), **data)
            sess.add(db_row)
            await sess.commit()
            await sess.refresh(db_row)
            return self._to_dict(db_row)

    async def get_inventory(self, item_id: UUID) -> dict[str, Any] | None:
        sess = await self._session()
        if sess is None:
            return self._inventory.get(str(item_id))
        async with sess:
            row = await sess.get(InventoryItem, item_id)
            return self._to_dict(row) if row else None

    async def list_inventory(self) -> list[dict[str, Any]]:
        sess = await self._session()
        if sess is None:
            return sorted(self._inventory.values(), key=lambda x: x.get("name", ""))
        async with sess:
            rows = (
                (await sess.execute(select(InventoryItem).order_by(InventoryItem.name)))
                .scalars()
                .all()
            )
            return [self._to_dict(r) for r in rows]

    async def update_inventory(self, item_id: UUID, data: dict[str, Any]) -> dict[str, Any] | None:
        sess = await self._session()
        if sess is None:
            iid = str(item_id)
            if iid not in self._inventory:
                return None
            self._inventory[iid].update(data)
            self._inventory[iid]["updated_at"] = datetime.now(UTC)
            return self._inventory[iid]
        async with sess:
            row = await sess.get(InventoryItem, item_id)
            if not row:
                return None
            for k, v in data.items():
                if v is not None:
                    setattr(row, k, v)
            row.updated_at = datetime.now(UTC)
            await sess.commit()
            await sess.refresh(row)
            return self._to_dict(row)

    async def delete_inventory(self, item_id: UUID) -> bool:
        sess = await self._session()
        if sess is None:
            return bool(self._inventory.pop(str(item_id), None))
        async with sess:
            row = await sess.get(InventoryItem, item_id)
            if not row:
                return False
            await sess.delete(row)
            await sess.commit()
            return True

    # ------------------------------------------------------------------
    # Electrical Estimations
    # ------------------------------------------------------------------
    async def create_estimation(self, data: dict[str, Any]) -> dict[str, Any]:
        items_data = data.pop("items", [])
        data["estimation_number"] = _next_number("EST")
        mat_cost = sum(
            Decimal(str(i.get("material_cost_per_unit", 0))) * Decimal(str(i.get("quantity", 0)))
            for i in items_data
        )
        lab_cost = sum(
            Decimal(str(i.get("labor_cost_per_unit", 0))) * Decimal(str(i.get("quantity", 0)))
            for i in items_data
        )
        data["total_materials_cost"] = mat_cost
        data["total_labor_cost"] = lab_cost
        data["total_overhead"] = (mat_cost + lab_cost) * Decimal("0.10")
        data["grand_total"] = mat_cost + lab_cost + data["total_overhead"]

        sess = await self._session()
        data.setdefault("status", "draft")
        if sess is None:
            row = data | {
                "id": uuid4(),
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "items": items_data,
            }
            self._estimations[str(row["id"])] = row
            return row
        async with sess:
            db_row = ElectricalEstimation(id=uuid4(), **data)
            sess.add(db_row)
            for item in items_data:
                item["total_cost"] = Decimal(str(item.get("material_cost_per_unit", 0))) * Decimal(
                    str(item.get("quantity", 0))
                ) + Decimal(str(item.get("labor_cost_per_unit", 0))) * Decimal(
                    str(item.get("quantity", 0))
                )
                sess.add(EstimationItem(estimation_id=db_row.id, **item))
            await sess.commit()
            await sess.refresh(db_row)
            return await self._estimation_to_dict(sess, db_row)

    async def get_estimation(self, estimation_id: UUID) -> dict[str, Any] | None:
        sess = await self._session()
        if sess is None:
            return self._estimations.get(str(estimation_id))
        async with sess:
            row = await sess.get(ElectricalEstimation, estimation_id)
            return await self._estimation_to_dict(sess, row) if row else None

    async def list_estimations(self) -> list[dict[str, Any]]:
        sess = await self._session()
        if sess is None:
            return sorted(
                self._estimations.values(), key=lambda x: x.get("created_at", ""), reverse=True
            )
        async with sess:
            rows = (
                (
                    await sess.execute(
                        select(ElectricalEstimation).order_by(
                            ElectricalEstimation.created_at.desc()
                        )
                    )
                )
                .scalars()
                .all()
            )
            return [await self._estimation_to_dict(sess, r) for r in rows]

    async def _estimation_to_dict(
        self, sess: AsyncSession, r: ElectricalEstimation
    ) -> dict[str, Any]:
        await sess.refresh(r, ["items"])
        d = self._to_dict(r)
        d["items"] = [self._to_dict(i) for i in r.items]
        return d

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------
    async def report_summary(self) -> dict[str, Any]:
        sess = await self._session()
        if sess is None:
            return {
                "customers": len(self._customers),
                "vendors": len(self._vendors),
                "quotations": len(self._quotations),
                "invoices": len(self._invoices),
                "inventory_items": len(self._inventory),
                "total_quoted": 0.0,
                "total_invoiced": 0.0,
                "total_outstanding": 0.0,
                "inventory_value": 0.0,
            }
        async with sess:
            customers = (await sess.execute(select(Customer))).scalars().all()
            vendors = (await sess.execute(select(Vendor))).scalars().all()
            quotations = (await sess.execute(select(Quotation))).scalars().all()
            invoices = (await sess.execute(select(Invoice))).scalars().all()
            inventory = (await sess.execute(select(InventoryItem))).scalars().all()

            total_quoted = sum(
                float(q.total_amount or 0) for q in quotations if q.status in ("sent", "accepted")
            )
            total_invoiced = sum(
                float(i.total_amount or 0) for i in invoices if i.status in ("sent", "paid")
            )
            total_outstanding = sum(
                float(i.total_amount or 0) for i in invoices if i.status == "sent"
            )
            inv_value = sum(float(i.unit_price or 0) * float(i.quantity or 0) for i in inventory)

            return {
                "customers": len(customers),
                "vendors": len(vendors),
                "quotations": len(quotations),
                "invoices": len(invoices),
                "inventory_items": len(inventory),
                "total_quoted": round(total_quoted, 2),
                "total_invoiced": round(total_invoiced, 2),
                "total_outstanding": round(total_outstanding, 2),
                "inventory_value": round(inv_value, 2),
            }


repo: BusinessRepository | None = None


def get_business_repository() -> BusinessRepository:
    global repo
    if repo is None:
        repo = BusinessRepository()
    return repo


def reset_business_repository() -> None:
    global repo
    repo = None
