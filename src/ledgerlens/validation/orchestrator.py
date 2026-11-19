"""Validation orchestrator - runs all validators and collects results."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_session
from ..db.models import Invoice, InvoiceLine, PurchaseOrder, Vendor
from .bank import validate_bank_details
from .dates import validate_all_dates
from .duplicates import check_exact_duplicate, check_near_duplicates
from .gstin import validate_gstin_full, validate_gstin_vendor_match
from .irn import validate_irn_from_invoice
from .po_ref import validate_po_reference
from .tax import validate_invoice_totals, validate_line_tax_arithmetic, validate_tax_type_vs_places
from .text_layer import validate_text_layer_consistency

if TYPE_CHECKING:
    from ..extraction.models import ExtractionResult


@dataclass
class ValidationResult:
    """Result of a validation check."""

    validator: str  # V1, V2, etc.
    passed: bool
    message: str
    details: dict | None = None


@dataclass
class ValidationSummary:
    """Summary of all validation results."""

    invoice_id: int
    invoice_number: str
    results: list[ValidationResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    def get_failed(self) -> list[ValidationResult]:
        return [r for r in self.results if not r.passed]


async def run_all_validations(
    invoice: Invoice,
    lines: list[InvoiceLine],
    po: PurchaseOrder | None = None,
    vendor: Vendor | None = None,
    session: AsyncSession | None = None,
    text_layer_text: str | None = None,
    extraction_result: "ExtractionResult | None" = None,
) -> ValidationSummary:
    """Run all validators (V1-V12) on an invoice."""
    summary = ValidationSummary(invoice_id=invoice.id, invoice_number=invoice.invoice_number)

    # Use provided session or create one
    if session is None:
        async with get_session() as session:
            return await _run_validations(
                session, summary, invoice, lines, po, vendor, text_layer_text, extraction_result
            )
    else:
        return await _run_validations(session, summary, invoice, lines, po, vendor, text_layer_text, extraction_result)


async def _run_validations(
    session: AsyncSession,
    summary: ValidationSummary,
    invoice: Invoice,
    lines: list[InvoiceLine],
    po: PurchaseOrder | None,
    vendor: Vendor | None,
    text_layer_text: str | None,
    extraction_result: "ExtractionResult | None" = None,
) -> ValidationSummary:
    """Internal validation runner."""
    # Get vendor if not provided
    if vendor is None:
        vendor_result = await session.execute(select(Vendor).where(Vendor.id == invoice.vendor_id))
        vendor = vendor_result.scalar_one_or_none()

    if not vendor:
        summary.results.append(
            ValidationResult(
                validator="V0", passed=False, message="Vendor not found", details={"vendor_id": invoice.vendor_id}
            )
        )
        return summary

    vendor_gstin = vendor.gstin

    # V1: GSTIN format and checksum
    for vr in validate_gstin_full(vendor_gstin):
        summary.results.append(
            ValidationResult(validator="V1", passed=vr.passed, message=vr.message, details=vr.details)
        )

    # V2: GSTIN matches vendor master
    vr = await validate_gstin_vendor_match(vendor_gstin, vendor.legal_name, session)
    summary.results.append(ValidationResult(validator="V2", passed=vr.passed, message=vr.message, details=vr.details))

    # V3: Tax type vs places of supply
    for vr in validate_tax_type_vs_places(invoice, lines):
        summary.results.append(
            ValidationResult(validator="V3", passed=vr.passed, message=vr.message, details=vr.details)
        )

    # V4: Tax arithmetic (line-level)
    for line in lines:
        for vr in validate_line_tax_arithmetic(line):
            summary.results.append(
                ValidationResult(validator="V4", passed=vr.passed, message=vr.message, details=vr.details)
            )

    # V5: Totals and rounding
    for vr in validate_invoice_totals(invoice, lines):
        summary.results.append(
            ValidationResult(validator="V5", passed=vr.passed, message=vr.message, details=vr.details)
        )

    # V6: IRN recomputation
    if invoice.irn:
        vr = validate_irn_from_invoice(invoice.irn, vendor_gstin, invoice.invoice_number, str(invoice.invoice_date))
        summary.results.append(
            ValidationResult(validator="V6", passed=vr.passed, message=vr.message, details=vr.details)
        )

    # V7: Date plausibility
    for vr in validate_all_dates(invoice, po):
        summary.results.append(
            ValidationResult(validator="V7", passed=vr.passed, message=vr.message, details=vr.details)
        )

    # V8: Exact duplicate
    vr = await check_exact_duplicate(vendor_gstin, invoice.invoice_number, invoice.invoice_date, session=session)
    summary.results.append(ValidationResult(validator="V8", passed=vr.passed, message=vr.message, details=vr.details))

    # V9: Near duplicate
    vr = await check_near_duplicates(
        vendor_gstin, invoice.grand_total, invoice.invoice_date, vendor.legal_name, session=session
    )
    summary.results.append(ValidationResult(validator="V9", passed=vr.passed, message=vr.message, details=vr.details))

    # V10: Bank details
    vr = await validate_bank_details(
        invoice.bank_account_name,
        invoice.bank_account_number,
        invoice.bank_ifsc,
        invoice.bank_name,
        vendor_gstin,
        session=session,
    )
    summary.results.append(ValidationResult(validator="V10", passed=vr.passed, message=vr.message, details=vr.details))

    # V11: PO reference
    if invoice.po_reference:
        vr = await validate_po_reference(invoice.po_reference, vendor_gstin, session=session)
        summary.results.append(
            ValidationResult(validator="V11", passed=vr.passed, message=vr.message, details=vr.details)
        )

    # V12: Text layer consistency
    if text_layer_text and extraction_result is not None:
        for vr in validate_text_layer_consistency(extraction_result, text_layer_text):
            summary.results.append(
                ValidationResult(validator="V12", passed=vr.passed, message=vr.message, details=vr.details)
            )

    return summary


def run_all_validations_sync(
    invoice: Invoice,
    lines: list[InvoiceLine],
    po: PurchaseOrder | None = None,
    vendor: Vendor | None = None,
    text_layer_text: str | None = None,
    extraction_result: "ExtractionResult | None" = None,
) -> ValidationSummary:
    """Synchronous version for testing."""
    import asyncio

    return asyncio.run(
        run_all_validations(
            invoice, lines, po, vendor, text_layer_text=text_layer_text, extraction_result=extraction_result
        )
    )


from sqlalchemy import select  # noqa: E402
