from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..persistence.models import GUID, Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Customer(Base):
    __tablename__ = "business_customers"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(256))
    phone: Mapped[str | None] = mapped_column(String(64))
    company: Mapped[str | None] = mapped_column(String(256))
    address: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class Vendor(Base):
    __tablename__ = "business_vendors"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    contact_person: Mapped[str | None] = mapped_column(String(256))
    email: Mapped[str | None] = mapped_column(String(256))
    phone: Mapped[str | None] = mapped_column(String(64))
    address: Mapped[str | None] = mapped_column(Text)
    payment_terms: Mapped[str | None] = mapped_column(String(256))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class Quotation(Base):
    __tablename__ = "business_quotations"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    customer_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("business_customers.id"), nullable=False, index=True
    )
    quote_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    customer: Mapped[Customer] = relationship()
    items: Mapped[list[QuotationItem]] = relationship(
        back_populates="quotation", cascade="all, delete-orphan", lazy="selectin"
    )


class QuotationItem(Base):
    __tablename__ = "business_quotation_items"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    quotation_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("business_quotations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("1.00"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    quotation: Mapped[Quotation] = relationship(back_populates="items")


class Invoice(Base):
    __tablename__ = "business_invoices"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    customer_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("business_customers.id"), nullable=False, index=True
    )
    invoice_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    customer: Mapped[Customer] = relationship()
    items: Mapped[list[InvoiceItem]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", lazy="selectin"
    )


class InvoiceItem(Base):
    __tablename__ = "business_invoice_items"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("business_invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("1.00"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    invoice: Mapped[Invoice] = relationship(back_populates="items")


class PurchaseOrder(Base):
    __tablename__ = "business_purchase_orders"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    vendor_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("business_vendors.id"), nullable=False, index=True
    )
    po_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    expected_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    vendor: Mapped[Vendor] = relationship()
    items: Mapped[list[PurchaseOrderItem]] = relationship(
        back_populates="purchase_order", cascade="all, delete-orphan", lazy="selectin"
    )


class PurchaseOrderItem(Base):
    __tablename__ = "business_po_items"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    po_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("business_purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("1.00"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="items")


class BOQ(Base):
    __tablename__ = "business_boqs"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    project_name: Mapped[str] = mapped_column(String(512), nullable=False)
    boq_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    items: Mapped[list[BOQItem]] = relationship(
        back_populates="boq", cascade="all, delete-orphan", lazy="selectin"
    )


class BOQItem(Base):
    __tablename__ = "business_boq_items"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    boq_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("business_boqs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_code: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("1.00"))
    unit: Mapped[str] = mapped_column(String(32), default="Each")
    unit_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    boq: Mapped[BOQ] = relationship(back_populates="items")


class InventoryItem(Base):
    __tablename__ = "business_inventory"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    item_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(128), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    unit: Mapped[str] = mapped_column(String(32), default="Each")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    reorder_level: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    vendor_id: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("business_vendors.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    vendor: Mapped[Vendor | None] = relationship()


class ElectricalEstimation(Base):
    __tablename__ = "business_estimations"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    project_name: Mapped[str] = mapped_column(String(512), nullable=False)
    estimation_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    total_materials_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_labor_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_overhead: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    grand_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    items: Mapped[list[EstimationItem]] = relationship(
        back_populates="estimation", cascade="all, delete-orphan", lazy="selectin"
    )


class EstimationItem(Base):
    __tablename__ = "business_estimation_items"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    estimation_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("business_estimations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_code: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("1.00"))
    unit: Mapped[str] = mapped_column(String(32), default="Each")
    material_cost_per_unit: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    labor_cost_per_unit: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    estimation: Mapped[ElectricalEstimation] = relationship(back_populates="items")
