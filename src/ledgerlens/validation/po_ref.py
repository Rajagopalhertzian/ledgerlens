"""V11: PO reference exists and belongs to the vendor."""

from dataclasses import dataclass

from ..db.database import get_session
from ..db.models import PurchaseOrder, Vendor


@dataclass
class ValidationResult:
    """Result of a validation check."""

    passed: bool
    message: str
    details: dict | None = None


async def validate_po_reference(po_reference: str, vendor_gstin: str, session=None) -> ValidationResult:
    """V11: Validate PO reference exists and belongs to the vendor."""
    if not po_reference:
        return ValidationResult(True, "No PO reference provided (optional)", {"po_reference": None})

    if session is None:
        async with get_session() as session:
            return await _validate_po_reference(session, po_reference, vendor_gstin)
    else:
        return await _validate_po_reference(session, po_reference, vendor_gstin)


async def _validate_po_reference(session, po_reference: str, vendor_gstin: str) -> ValidationResult:
    """Internal PO reference validation."""
    # Find PO by number
    result = await session.execute(select(PurchaseOrder).where(PurchaseOrder.po_number == po_reference))
    po = result.scalar_one_or_none()

    if not po:
        return ValidationResult(
            False, f"PO {po_reference} not found", {"po_reference": po_reference, "vendor_gstin": vendor_gstin}
        )

    # Check if PO belongs to the vendor
    vendor_result = await session.execute(select(Vendor).where(Vendor.id == po.vendor_id))
    vendor = vendor_result.scalar_one_or_none()

    if not vendor:
        return ValidationResult(
            False, f"PO {po_reference} has invalid vendor", {"po_reference": po_reference, "po_vendor_id": po.vendor_id}
        )

    if vendor.gstin != vendor_gstin:
        return ValidationResult(
            False,
            f"PO {po_reference} belongs to different vendor: {vendor.gstin} (expected {vendor_gstin})",
            {
                "po_reference": po_reference,
                "po_vendor_gstin": vendor.gstin,
                "invoice_vendor_gstin": vendor_gstin,
                "po_vendor_name": vendor.legal_name,
            },
        )

    # Check PO status
    if po.status.value in ("closed", "complete"):
        return ValidationResult(
            False,
            f"PO {po_reference} is {po.status.value} (no further invoices expected)",
            {"po_reference": po_reference, "po_status": po.status.value},
        )

    return ValidationResult(
        True,
        f"PO {po_reference} valid and belongs to vendor {vendor_gstin}",
        {
            "po_reference": po_reference,
            "po_id": po.id,
            "po_status": po.status.value,
            "vendor_gstin": vendor_gstin,
            "vendor_name": vendor.legal_name,
        },
    )


def validate_po_reference_sync(po_reference: str, vendor_gstin: str) -> ValidationResult:
    """Synchronous version for testing."""
    import asyncio

    return asyncio.run(validate_po_reference(po_reference, vendor_gstin))


from sqlalchemy import select  # noqa: E402
