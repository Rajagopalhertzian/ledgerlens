"""Read tools for ERP MCP server."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ledgerlens.db.database import get_session
from ledgerlens.db.models import GoodsReceipt, GRNLine, Invoice, POLine, PurchaseOrder, Vendor
from ledgerlens.validation.irn import extract_fin_year


@dataclass
class ToolResult:
    """Result of a tool call."""

    success: bool
    data: dict | None = None
    error: str | None = None


# Tool: find_vendor_by_gstin
async def find_vendor_by_gstin(gstin: str, session: AsyncSession | None = None) -> ToolResult:
    """Find vendor by GSTIN."""
    if session is None:
        async with get_session() as session:
            return await _find_vendor_by_gstin(session, gstin)
    else:
        return await _find_vendor_by_gstin(session, gstin)


async def _find_vendor_by_gstin(session: AsyncSession, gstin: str) -> ToolResult:
    result = await session.execute(select(Vendor).where(Vendor.gstin == gstin.strip().upper(), Vendor.is_active))
    vendor = result.scalar_one_or_none()

    if not vendor:
        return ToolResult(success=False, error=f"Vendor with GSTIN {gstin} not found")

    return ToolResult(
        success=True,
        data={
            "vendor_id": vendor.id,
            "gstin": vendor.gstin,
            "legal_name": vendor.legal_name,
            "trade_name": vendor.trade_name,
            "address_line1": vendor.address_line1,
            "address_line2": vendor.address_line2,
            "city": vendor.city,
            "state_code": vendor.state_code,
            "pincode": vendor.pincode,
            "country": vendor.country,
            "bank_account_name": vendor.bank_account_name,
            "bank_account_number": vendor.bank_account_number,
            "bank_ifsc": vendor.bank_ifsc,
            "bank_name": vendor.bank_name,
            "contact_person": vendor.contact_person,
            "contact_email": vendor.contact_email,
            "contact_phone": vendor.contact_phone,
            "pan": vendor.pan,
            "is_active": vendor.is_active,
            "created_at": vendor.created_at.isoformat() if vendor.created_at else None,
        },
    )


# Tool: get_vendor
async def get_vendor(vendor_id: int, session: AsyncSession | None = None) -> ToolResult:
    """Get vendor by ID."""
    if session is None:
        async with get_session() as session:
            return await _get_vendor(session, vendor_id)
    else:
        return await _get_vendor(session, vendor_id)


async def _get_vendor(session: AsyncSession, vendor_id: int) -> ToolResult:
    result = await session.execute(select(Vendor).where(Vendor.id == vendor_id))
    vendor = result.scalar_one_or_none()

    if not vendor:
        return ToolResult(success=False, error=f"Vendor {vendor_id} not found")

    return ToolResult(
        success=True,
        data={
            "vendor_id": vendor.id,
            "gstin": vendor.gstin,
            "legal_name": vendor.legal_name,
            "trade_name": vendor.trade_name,
            "address_line1": vendor.address_line1,
            "address_line2": vendor.address_line2,
            "city": vendor.city,
            "state_code": vendor.state_code,
            "pincode": vendor.pincode,
            "country": vendor.country,
            "bank_account_name": vendor.bank_account_name,
            "bank_account_number": vendor.bank_account_number,
            "bank_ifsc": vendor.bank_ifsc,
            "bank_name": vendor.bank_name,
            "contact_person": vendor.contact_person,
            "contact_email": vendor.contact_email,
            "contact_phone": vendor.contact_phone,
            "pan": vendor.pan,
            "is_active": vendor.is_active,
            "created_at": vendor.created_at.isoformat() if vendor.created_at else None,
        },
    )


# Tool: get_po
async def get_po(po_id: int, session: AsyncSession | None = None) -> ToolResult:
    """Get purchase order by ID."""
    if session is None:
        async with get_session() as session:
            return await _get_po(session, po_id)
    else:
        return await _get_po(session, po_id)


async def _get_po(session: AsyncSession, po_id: int) -> ToolResult:
    result = await session.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))
    po = result.scalar_one_or_none()

    if not po:
        return ToolResult(success=False, error=f"PO {po_id} not found")

    # Get lines
    lines_result = await session.execute(select(POLine).where(POLine.po_id == po_id))
    lines = lines_result.scalars().all()

    return ToolResult(
        success=True,
        data={
            "po_id": po.id,
            "po_number": po.po_number,
            "vendor_id": po.vendor_id,
            "po_date": str(po.po_date),
            "delivery_date": str(po.delivery_date) if po.delivery_date else None,
            "buyer_gstin": po.buyer_gstin,
            "buyer_name": po.buyer_name,
            "buyer_address": po.buyer_address,
            "buyer_state_code": po.buyer_state_code,
            "place_of_supply": po.place_of_supply,
            "status": po.status.value,
            "currency": po.currency,
            "subtotal": str(po.subtotal),
            "total_tax": str(po.total_tax),
            "grand_total": str(po.grand_total),
            "notes": po.notes,
            "lines": [
                {
                    "line_id": l.id,
                    "line_number": l.line_number,
                    "item_code": l.item_code,
                    "item_description": l.item_description,
                    "hsn_code": l.hsn_code,
                    "uom": l.uom,
                    "quantity": str(l.quantity),
                    "unit_price": str(l.unit_price),
                    "discount_percent": str(l.discount_percent),
                    "tax_rate": str(l.tax_rate),
                    "tax_type": l.tax_type.value,
                    "taxable_value": str(l.taxable_value),
                    "tax_amount": str(l.tax_amount),
                    "line_total": str(l.line_total),
                }
                for l in lines
            ],
            "created_at": po.created_at.isoformat() if po.created_at else None,
        },
    )


# Tool: search_pos
async def search_pos(
    vendor_gstin: str | None = None,
    po_number: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession | None = None,
) -> ToolResult:
    """Search purchase orders."""
    if session is None:
        async with get_session() as session:
            return await _search_pos(session, vendor_gstin, po_number, status, date_from, date_to, limit, offset)
    else:
        return await _search_pos(session, vendor_gstin, po_number, status, date_from, date_to, limit, offset)


async def _search_pos(
    session: AsyncSession,
    vendor_gstin: str | None,
    po_number: str | None,
    status: str | None,
    date_from: str | None,
    date_to: str | None,
    limit: int,
    offset: int,
) -> ToolResult:
    from sqlalchemy import and_

    conditions = []
    if vendor_gstin:
        vendor_result = await session.execute(select(Vendor.id).where(Vendor.gstin == vendor_gstin.strip().upper()))
        vendor_id = vendor_result.scalar_one_or_none()
        if vendor_id:
            conditions.append(PurchaseOrder.vendor_id == vendor_id)
        else:
            return ToolResult(success=True, data={"pos": [], "total": 0})

    if po_number:
        conditions.append(PurchaseOrder.po_number.ilike(f"%{po_number}%"))

    if status:
        conditions.append(PurchaseOrder.status == status)

    if date_from:
        conditions.append(PurchaseOrder.po_date >= date_from)

    if date_to:
        conditions.append(PurchaseOrder.po_date <= date_to)

    query = select(PurchaseOrder)
    if conditions:
        query = query.where(and_(*conditions))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar()

    # Get paginated results
    query = query.order_by(PurchaseOrder.po_date.desc()).limit(limit).offset(offset)
    result = await session.execute(query)
    pos = result.scalars().all()

    return ToolResult(
        success=True,
        data={
            "pos": [
                {
                    "po_id": po.id,
                    "po_number": po.po_number,
                    "vendor_id": po.vendor_id,
                    "po_date": str(po.po_date),
                    "status": po.status.value,
                    "grand_total": str(po.grand_total),
                }
                for po in pos
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    )


# Tool: get_grn
async def get_grn(grn_id: int, session: AsyncSession | None = None) -> ToolResult:
    """Get goods receipt by ID."""
    if session is None:
        async with get_session() as session:
            return await _get_grn(session, grn_id)
    else:
        return await _get_grn(session, grn_id)


async def _get_grn(session: AsyncSession, grn_id: int) -> ToolResult:
    result = await session.execute(select(GoodsReceipt).where(GoodsReceipt.id == grn_id))
    grn = result.scalar_one_or_none()

    if not grn:
        return ToolResult(success=False, error=f"GRN {grn_id} not found")

    # Get lines
    lines_result = await session.execute(select(GRNLine).where(GRNLine.grn_id == grn_id))
    lines = lines_result.scalars().all()

    return ToolResult(
        success=True,
        data={
            "grn_id": grn.id,
            "grn_number": grn.grn_number,
            "po_id": grn.po_id,
            "vendor_id": grn.vendor_id,
            "grn_date": str(grn.grn_date),
            "status": grn.status.value,
            "received_by": grn.received_by,
            "notes": grn.notes,
            "lines": [
                {
                    "line_id": l.id,
                    "line_number": l.line_number,
                    "po_line_id": l.po_line_id,
                    "quantity_received": str(l.quantity_received),
                    "quantity_accepted": str(l.quantity_accepted),
                    "quantity_rejected": str(l.quantity_rejected),
                    "notes": l.notes,
                }
                for l in lines
            ],
            "created_at": grn.created_at.isoformat() if grn.created_at else None,
        },
    )


# Tool: get_invoice_history
async def get_invoice_history(
    vendor_gstin: str | None = None,
    vendor_id: int | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession | None = None,
) -> ToolResult:
    """Get invoice history."""
    if session is None:
        async with get_session() as session:
            return await _get_invoice_history(
                session, vendor_gstin, vendor_id, status, date_from, date_to, limit, offset
            )
    else:
        return await _get_invoice_history(session, vendor_gstin, vendor_id, status, date_from, date_to, limit, offset)


async def _get_invoice_history(
    session: AsyncSession,
    vendor_gstin: str | None,
    vendor_id: int | None,
    status: str | None,
    date_from: str | None,
    date_to: str | None,
    limit: int,
    offset: int,
) -> ToolResult:
    from sqlalchemy import and_

    conditions = []

    if vendor_gstin:
        vendor_result = await session.execute(select(Vendor.id).where(Vendor.gstin == vendor_gstin.strip().upper()))
        vid = vendor_result.scalar_one_or_none()
        if vid:
            conditions.append(Invoice.vendor_id == vid)
        else:
            return ToolResult(success=True, data={"invoices": [], "total": 0})
    elif vendor_id:
        conditions.append(Invoice.vendor_id == vendor_id)

    if status:
        conditions.append(Invoice.status == status)

    if date_from:
        conditions.append(Invoice.invoice_date >= date_from)

    if date_to:
        conditions.append(Invoice.invoice_date <= date_to)

    query = select(Invoice)
    if conditions:
        query = query.where(and_(*conditions))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar()

    # Get paginated results
    query = query.order_by(Invoice.invoice_date.desc()).limit(limit).offset(offset)
    result = await session.execute(query)
    invoices = result.scalars().all()

    return ToolResult(
        success=True,
        data={
            "invoices": [
                {
                    "invoice_id": inv.id,
                    "invoice_number": inv.invoice_number,
                    "vendor_id": inv.vendor_id,
                    "invoice_date": str(inv.invoice_date),
                    "status": inv.status.value,
                    "grand_total": str(inv.grand_total),
                    "po_reference": inv.po_reference,
                    "grn_reference": inv.grn_reference,
                }
                for inv in invoices
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    )


# Tool: check_duplicate
async def check_duplicate(
    vendor_gstin: str,
    invoice_number: str,
    invoice_date: str,
    doc_type: str = "INV",
    session: AsyncSession | None = None,
) -> ToolResult:
    """Check for exact duplicate invoice."""
    if session is None:
        async with get_session() as session:
            return await _check_duplicate(session, vendor_gstin, invoice_number, invoice_date, doc_type)
    else:
        return await _check_duplicate(session, vendor_gstin, invoice_number, invoice_date, doc_type)


async def _check_duplicate(
    session: AsyncSession, vendor_gstin: str, invoice_number: str, invoice_date: str, doc_type: str
) -> ToolResult:
    # Get vendor
    vendor_result = await session.execute(select(Vendor.id).where(Vendor.gstin == vendor_gstin.strip().upper()))
    vendor_id = vendor_result.scalar_one_or_none()

    if not vendor_id:
        return ToolResult(success=True, data={"is_duplicate": False, "reason": "Vendor not found"})

    fin_year = extract_fin_year(invoice_date)

    # Check existing invoice with same vendor, FY, and number
    result = await session.execute(
        select(Invoice).where(Invoice.vendor_id == vendor_id, Invoice.invoice_number == invoice_number)
    )
    existing = result.scalars().all()

    for inv in existing:
        inv_fy = extract_fin_year(str(inv.invoice_date))
        if inv_fy == fin_year:
            return ToolResult(
                success=True,
                data={
                    "is_duplicate": True,
                    "existing_invoice_id": inv.id,
                    "existing_invoice_number": inv.invoice_number,
                    "existing_invoice_date": str(inv.invoice_date),
                },
            )

    return ToolResult(success=True, data={"is_duplicate": False})
