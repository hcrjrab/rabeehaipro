from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException

from . import models  # noqa: F401 — register models with Base.metadata before init_db
from .repository import get_business_repository
from .schemas import (
    BOQCreate,
    BOQResponse,
    CustomerCreate,
    CustomerResponse,
    CustomerUpdate,
    EstimationCreate,
    EstimationResponse,
    InventoryCreate,
    InventoryResponse,
    InventoryUpdate,
    InvoiceCreate,
    InvoiceResponse,
    PurchaseOrderCreate,
    PurchaseOrderResponse,
    QuotationCreate,
    QuotationResponse,
    VendorCreate,
    VendorResponse,
    VendorUpdate,
)

router = APIRouter(prefix="/business", tags=["business"])
repo = get_business_repository()


# ------------------------------------------------------------------
# Customers
# ------------------------------------------------------------------
@router.get("/customers", response_model=list[CustomerResponse])
async def list_customers() -> Any:
    return await repo.list_customers()


@router.post("/customers", response_model=CustomerResponse, status_code=201)
async def create_customer(body: CustomerCreate) -> Any:
    return await repo.create_customer(body.model_dump(exclude_unset=True))


@router.get("/customers/{customer_id}", response_model=CustomerResponse)
async def get_customer(customer_id: UUID) -> Any:
    result = await repo.get_customer(customer_id)
    if not result:
        raise HTTPException(404, "Customer not found")
    return result


@router.patch("/customers/{customer_id}", response_model=CustomerResponse)
async def update_customer(customer_id: UUID, body: CustomerUpdate) -> Any:
    result = await repo.update_customer(
        customer_id, body.model_dump(exclude_unset=True, exclude_none=True)
    )
    if not result:
        raise HTTPException(404, "Customer not found")
    return result


@router.delete("/customers/{customer_id}", status_code=204)
async def delete_customer(customer_id: UUID) -> None:
    ok = await repo.delete_customer(customer_id)
    if not ok:
        raise HTTPException(404, "Customer not found")


# ------------------------------------------------------------------
# Vendors
# ------------------------------------------------------------------
@router.get("/vendors", response_model=list[VendorResponse])
async def list_vendors() -> Any:
    return await repo.list_vendors()


@router.post("/vendors", response_model=VendorResponse, status_code=201)
async def create_vendor(body: VendorCreate) -> Any:
    return await repo.create_vendor(body.model_dump(exclude_unset=True))


@router.get("/vendors/{vendor_id}", response_model=VendorResponse)
async def get_vendor(vendor_id: UUID) -> Any:
    result = await repo.get_vendor(vendor_id)
    if not result:
        raise HTTPException(404, "Vendor not found")
    return result


@router.patch("/vendors/{vendor_id}", response_model=VendorResponse)
async def update_vendor(vendor_id: UUID, body: VendorUpdate) -> Any:
    result = await repo.update_vendor(
        vendor_id, body.model_dump(exclude_unset=True, exclude_none=True)
    )
    if not result:
        raise HTTPException(404, "Vendor not found")
    return result


@router.delete("/vendors/{vendor_id}", status_code=204)
async def delete_vendor(vendor_id: UUID) -> None:
    ok = await repo.delete_vendor(vendor_id)
    if not ok:
        raise HTTPException(404, "Vendor not found")


# ------------------------------------------------------------------
# Quotations
# ------------------------------------------------------------------
@router.get("/quotations", response_model=list[QuotationResponse])
async def list_quotations() -> Any:
    return await repo.list_quotations()


@router.post("/quotations", response_model=QuotationResponse, status_code=201)
async def create_quotation(body: QuotationCreate) -> Any:
    return await repo.create_quotation(body.model_dump(exclude_unset=True))


@router.get("/quotations/{quotation_id}", response_model=QuotationResponse)
async def get_quotation(quotation_id: UUID) -> Any:
    result = await repo.get_quotation(quotation_id)
    if not result:
        raise HTTPException(404, "Quotation not found")
    return result


# ------------------------------------------------------------------
# Invoices
# ------------------------------------------------------------------
@router.get("/invoices", response_model=list[InvoiceResponse])
async def list_invoices() -> Any:
    return await repo.list_invoices()


@router.post("/invoices", response_model=InvoiceResponse, status_code=201)
async def create_invoice(body: InvoiceCreate) -> Any:
    return await repo.create_invoice(body.model_dump(exclude_unset=True))


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(invoice_id: UUID) -> Any:
    result = await repo.get_invoice(invoice_id)
    if not result:
        raise HTTPException(404, "Invoice not found")
    return result


# ------------------------------------------------------------------
# Purchase Orders
# ------------------------------------------------------------------
@router.get("/purchase-orders", response_model=list[PurchaseOrderResponse])
async def list_purchase_orders() -> Any:
    return await repo.list_purchase_orders()


@router.post("/purchase-orders", response_model=PurchaseOrderResponse, status_code=201)
async def create_purchase_order(body: PurchaseOrderCreate) -> Any:
    return await repo.create_purchase_order(body.model_dump(exclude_unset=True))


@router.get("/purchase-orders/{po_id}", response_model=PurchaseOrderResponse)
async def get_purchase_order(po_id: UUID) -> Any:
    result = await repo.get_purchase_order(po_id)
    if not result:
        raise HTTPException(404, "Purchase order not found")
    return result


# ------------------------------------------------------------------
# BOQ
# ------------------------------------------------------------------
@router.get("/boq", response_model=list[BOQResponse])
async def list_boqs() -> Any:
    return await repo.list_boqs()


@router.post("/boq", response_model=BOQResponse, status_code=201)
async def create_boq(body: BOQCreate) -> Any:
    return await repo.create_boq(body.model_dump(exclude_unset=True))


@router.get("/boq/{boq_id}", response_model=BOQResponse)
async def get_boq(boq_id: UUID) -> Any:
    result = await repo.get_boq(boq_id)
    if not result:
        raise HTTPException(404, "BOQ not found")
    return result


# ------------------------------------------------------------------
# Inventory
# ------------------------------------------------------------------
@router.get("/inventory", response_model=list[InventoryResponse])
async def list_inventory() -> Any:
    return await repo.list_inventory()


@router.post("/inventory", response_model=InventoryResponse, status_code=201)
async def create_inventory(body: InventoryCreate) -> Any:
    return await repo.create_inventory(body.model_dump(exclude_unset=True))


@router.get("/inventory/{item_id}", response_model=InventoryResponse)
async def get_inventory(item_id: UUID) -> Any:
    result = await repo.get_inventory(item_id)
    if not result:
        raise HTTPException(404, "Inventory item not found")
    return result


@router.patch("/inventory/{item_id}", response_model=InventoryResponse)
async def update_inventory(item_id: UUID, body: InventoryUpdate) -> Any:
    result = await repo.update_inventory(
        item_id, body.model_dump(exclude_unset=True, exclude_none=True)
    )
    if not result:
        raise HTTPException(404, "Inventory item not found")
    return result


@router.delete("/inventory/{item_id}", status_code=204)
async def delete_inventory(item_id: UUID) -> None:
    ok = await repo.delete_inventory(item_id)
    if not ok:
        raise HTTPException(404, "Inventory item not found")


# ------------------------------------------------------------------
# Electrical Estimations
# ------------------------------------------------------------------
@router.get("/estimations", response_model=list[EstimationResponse])
async def list_estimations() -> Any:
    return await repo.list_estimations()


@router.post("/estimations", response_model=EstimationResponse, status_code=201)
async def create_estimation(body: EstimationCreate) -> Any:
    return await repo.create_estimation(body.model_dump(exclude_unset=True))


@router.get("/estimations/{estimation_id}", response_model=EstimationResponse)
async def get_estimation(estimation_id: UUID) -> Any:
    result = await repo.get_estimation(estimation_id)
    if not result:
        raise HTTPException(404, "Estimation not found")
    return result


# ------------------------------------------------------------------
# Reports
# ------------------------------------------------------------------
@router.get("/reports/summary")
async def report_summary() -> Any:
    return await repo.report_summary()
