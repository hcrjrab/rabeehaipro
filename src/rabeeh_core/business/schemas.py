from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BusinessStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PAID = "paid"
    OVERDUE = "overdue"
    RECEIVED = "received"
    CANCELLED = "cancelled"
    FINAL = "final"
    APPROVED = "approved"
    EXPIRED = "expired"


class CustomerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=256)
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    address: str | None = None
    notes: str | None = None


class CustomerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    address: str | None = None
    notes: str | None = None


class CustomerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    address: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class VendorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=256)
    contact_person: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    payment_terms: str | None = None
    notes: str | None = None


class VendorUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    contact_person: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    payment_terms: str | None = None
    notes: str | None = None


class VendorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    contact_person: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    payment_terms: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    description: str
    quantity: Decimal = Decimal("1.00")
    unit_price: Decimal = Decimal("0.00")
    total: Decimal = Decimal("0.00")


class QuotationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: UUID
    title: str = ""
    status: str = "draft"
    valid_until: datetime | None = None
    notes: str | None = None
    items: list[LineItem] = Field(default_factory=list)


class QuotationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    customer_id: UUID
    quote_number: str
    title: str
    status: str
    subtotal: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    valid_until: datetime | None = None
    notes: str | None = None
    items: list[LineItem] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class InvoiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: UUID
    status: str = "draft"
    tax_rate: Decimal = Decimal("0.00")
    due_date: datetime | None = None
    notes: str | None = None
    items: list[LineItem] = Field(default_factory=list)


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    customer_id: UUID
    invoice_number: str
    status: str
    subtotal: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    due_date: datetime | None = None
    notes: str | None = None
    items: list[LineItem] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class PurchaseOrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor_id: UUID
    status: str = "draft"
    tax_rate: Decimal = Decimal("0.00")
    expected_date: datetime | None = None
    notes: str | None = None
    items: list[LineItem] = Field(default_factory=list)


class PurchaseOrderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    vendor_id: UUID
    po_number: str
    status: str
    subtotal: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    expected_date: datetime | None = None
    notes: str | None = None
    items: list[LineItem] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class BOQItemSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    item_code: str = ""
    description: str
    quantity: Decimal = Decimal("1.00")
    unit: str = "Each"
    unit_rate: Decimal = Decimal("0.00")
    amount: Decimal = Decimal("0.00")


class BOQCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_name: str = Field(..., min_length=1, max_length=512)
    status: str = "draft"
    notes: str | None = None
    items: list[BOQItemSchema] = Field(default_factory=list)


class BOQResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    project_name: str
    boq_number: str
    status: str
    notes: str | None = None
    items: list[BOQItemSchema] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class InventoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_code: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=256)
    description: str | None = None
    category: str | None = None
    quantity: Decimal = Decimal("0.00")
    unit: str = "Each"
    unit_price: Decimal = Decimal("0.00")
    reorder_level: Decimal = Decimal("0.00")
    vendor_id: UUID | None = None


class InventoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    category: str | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    reorder_level: Decimal | None = None
    vendor_id: UUID | None = None


class InventoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    item_code: str
    name: str
    description: str | None = None
    category: str | None = None
    quantity: Decimal
    unit: str
    unit_price: Decimal
    reorder_level: Decimal
    vendor_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class EstimationItemSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    item_code: str = ""
    description: str
    quantity: Decimal = Decimal("1.00")
    unit: str = "Each"
    material_cost_per_unit: Decimal = Decimal("0.00")
    labor_cost_per_unit: Decimal = Decimal("0.00")
    total_cost: Decimal = Decimal("0.00")


class EstimationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_name: str = Field(..., min_length=1, max_length=512)
    status: str = "draft"
    notes: str | None = None
    items: list[EstimationItemSchema] = Field(default_factory=list)


class EstimationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    project_name: str
    estimation_number: str
    status: str
    total_materials_cost: Decimal
    total_labor_cost: Decimal
    total_overhead: Decimal
    grand_total: Decimal
    notes: str | None = None
    items: list[EstimationItemSchema] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
