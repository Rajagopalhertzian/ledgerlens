"""V8: Exact duplicate detection (supplier GSTIN + FY + doc type + number).
V9: Near-duplicate detection (vendor + amount + date proximity, fuzzy).
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from rapidfuzz import fuzz

from ..db.database import get_session
from ..db.models import Invoice
from .irn import extract_fin_year


@dataclass
class ValidationResult:
    """Result of a validation check."""

    passed: bool
    message: str
    details: dict | None = None


@dataclass
class DuplicateMatch:
    """Represents a duplicate match."""

    invoice_id: int
    invoice_number: str
    vendor_gstin: str
    invoice_date: date
    grand_total: Decimal
    match_type: str  # "exact" or "near"
    similarity: float


async def check_exact_duplicate(
    vendor_gstin: str, invoice_number: str, invoice_date: date, doc_type: str = "INV", session=None
) -> ValidationResult:
    """V8: Check for exact duplicate by identity (GSTIN + FY + doc type + number)."""
    fin_year = extract_fin_year(str(invoice_date))
    identity_key = f"{vendor_gstin}{fin_year}{doc_type}{invoice_number}"

    if session is None:
        async with get_session() as session:
            return await _check_exact_duplicate(session, identity_key, vendor_gstin, invoice_number, invoice_date)
    else:
        return await _check_exact_duplicate(session, identity_key, vendor_gstin, invoice_number, invoice_date)


async def _check_exact_duplicate(
    session, identity_key: str, vendor_gstin: str, invoice_number: str, invoice_date: date
) -> ValidationResult:
    """Internal exact duplicate check."""
    # Check existing invoices with same vendor, FY, and number
    fin_year = extract_fin_year(str(invoice_date))

    result = await session.execute(
        select(Invoice).where(
            Invoice.vendor_id.in_(select(Vendor.id).where(Vendor.gstin == vendor_gstin)),
            Invoice.invoice_number == invoice_number,
        )
    )
    existing = result.scalars().all()

    if existing:
        # Check if same FY
        for inv in existing:
            inv_fy = extract_fin_year(str(inv.invoice_date))
            if inv_fy == fin_year:
                return ValidationResult(
                    False,
                    f"Exact duplicate found: {vendor_gstin} + {fin_year} + {invoice_number}",
                    {
                        "match_type": "exact",
                        "existing_invoice_id": inv.id,
                        "existing_invoice_number": inv.invoice_number,
                        "identity_key": identity_key,
                    },
                )

    return ValidationResult(True, "No exact duplicate found", {"identity_key": identity_key})


async def check_near_duplicates(
    vendor_gstin: str,
    grand_total: Decimal,
    invoice_date: date,
    vendor_name: str | None = None,
    amount_tolerance_pct: float = 1.0,
    date_window_days: int = 7,
    session=None,
) -> ValidationResult:
    """V9: Check for near-duplicates (similar vendor + amount + date proximity)."""
    if session is None:
        async with get_session() as session:
            return await _check_near_duplicates(
                session, vendor_gstin, grand_total, invoice_date, vendor_name, amount_tolerance_pct, date_window_days
            )
    else:
        return await _check_near_duplicates(
            session, vendor_gstin, grand_total, invoice_date, vendor_name, amount_tolerance_pct, date_window_days
        )


async def _check_near_duplicates(
    session,
    vendor_gstin: str,
    grand_total: Decimal,
    invoice_date: date,
    vendor_name: str | None,
    amount_tolerance_pct: float,
    date_window_days: int,
) -> ValidationResult:
    """Internal near-duplicate check."""
    from sqlalchemy import and_

    # Get vendor ID
    vendor_result = await session.execute(select(Vendor.id).where(Vendor.gstin == vendor_gstin))
    vendor = vendor_result.scalar_one_or_none()

    if not vendor:
        return ValidationResult(False, f"Vendor {vendor_gstin} not found", {"vendor_gstin": vendor_gstin})

    # Search for invoices within date window and amount tolerance
    date_start = invoice_date - timedelta(days=date_window_days)
    date_end = invoice_date + timedelta(days=date_window_days)

    amount_lower = grand_total * (Decimal("1") - Decimal(str(amount_tolerance_pct)) / Decimal("100"))
    amount_upper = grand_total * (Decimal("1") + Decimal(str(amount_tolerance_pct)) / Decimal("100"))

    result = await session.execute(
        select(Invoice).where(
            and_(
                Invoice.vendor_id == vendor,
                Invoice.invoice_date >= date_start,
                Invoice.invoice_date <= date_end,
                Invoice.grand_total >= amount_lower,
                Invoice.grand_total <= amount_upper,
            )
        )
    )
    candidates = result.scalars().all()

    matches = []
    for inv in candidates:
        # Calculate similarity
        amount_sim = 1.0 - float(abs(inv.grand_total - grand_total) / grand_total)

        name_sim = 1.0
        if vendor_name and inv.vendor:
            name_sim = fuzz.ratio(vendor_name.upper(), inv.vendor.legal_name.upper()) / 100.0

        # Combined similarity
        combined_sim = (amount_sim * 0.7) + (name_sim * 0.3)

        if combined_sim > 0.8:
            matches.append(
                DuplicateMatch(
                    invoice_id=inv.id,
                    invoice_number=inv.invoice_number,
                    vendor_gstin=inv.vendor.gstin if inv.vendor else "Unknown",
                    invoice_date=inv.invoice_date,
                    grand_total=inv.grand_total,
                    match_type="near",
                    similarity=combined_sim,
                )
            )

    if matches:
        best_match = max(matches, key=lambda m: m.similarity)
        return ValidationResult(
            False,
            f"Near duplicate found: {best_match.invoice_number} (similarity: {best_match.similarity:.2f})",
            {
                "match_type": "near",
                "matches": [
                    {
                        "invoice_id": m.invoice_id,
                        "invoice_number": m.invoice_number,
                        "date": str(m.invoice_date),
                        "amount": str(m.grand_total),
                        "similarity": m.similarity,
                    }
                    for m in matches
                ],
                "best_match": {"invoice_id": best_match.invoice_id, "similarity": best_match.similarity},
            },
        )

    return ValidationResult(
        True,
        "No near duplicates found",
        {
            "searched_vendor": vendor_gstin,
            "amount_range": f"{amount_lower} - {amount_upper}",
            "date_range": f"{date_start} - {date_end}",
        },
    )


# Synchronous versions for testing
def check_exact_duplicate_sync(
    vendor_gstin: str, invoice_number: str, invoice_date: date, doc_type: str = "INV"
) -> ValidationResult:
    import asyncio

    return asyncio.run(check_exact_duplicate(vendor_gstin, invoice_number, invoice_date, doc_type))


def check_near_duplicates_sync(
    vendor_gstin: str,
    grand_total: Decimal,
    invoice_date: date,
    vendor_name: str | None = None,
    amount_tolerance_pct: float = 1.0,
    date_window_days: int = 7,
) -> ValidationResult:
    import asyncio

    return asyncio.run(
        check_near_duplicates(
            vendor_gstin, grand_total, invoice_date, vendor_name, amount_tolerance_pct, date_window_days
        )
    )


from sqlalchemy import select  # noqa: E402

from ..db.models import Vendor  # noqa: E402
