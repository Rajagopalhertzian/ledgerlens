"""Entity resolution for vendors and POs."""

from decimal import Decimal

from rapidfuzz import fuzz, process
from sqlalchemy import select

from ..db.database import get_session
from ..db.models import PurchaseOrder, Vendor
from .models import POCandidate, VendorMatchResult

# Thresholds for fuzzy matching
VENDOR_NAME_THRESHOLD = 85
VENDOR_ADDRESS_THRESHOLD = 80
PO_AMOUNT_THRESHOLD = 5.0  # percentage
PO_DATE_WINDOW_DAYS = 30


async def resolve_vendor(gstin: str | None, name: str | None, address: str | None, session=None) -> VendorMatchResult:
    """Resolve vendor from GSTIN, name, and address.

    Priority:
    1. Exact GSTIN match
    2. Fuzzy name + address match
    """
    if session is None:
        async with get_session() as session:
            return await _resolve_vendor(session, gstin, name, address)
    else:
        return await _resolve_vendor(session, gstin, name, address)


async def _resolve_vendor(session, gstin: str | None, name: str | None, address: str | None) -> VendorMatchResult:
    """Internal vendor resolution."""
    # 1. Exact GSTIN match (highest priority)
    if gstin:
        gstin = gstin.strip().upper()
        result = await session.execute(select(Vendor).where(Vendor.gstin == gstin, Vendor.is_active == True))
        vendor = result.scalar_one_or_none()
        if vendor:
            return VendorMatchResult(
                vendor_id=vendor.id,
                vendor_gstin=vendor.gstin,
                vendor_name=vendor.legal_name,
                match_type="exact_gstin",
                confidence=1.0,
            )

    # 2. Fuzzy match on name + address
    if name:
        # Get all active vendors
        result = await session.execute(select(Vendor).where(Vendor.is_active == True))
        vendors = result.scalars().all()

        if vendors:
            # Build name+address strings for comparison
            vendor_strings = []
            for v in vendors:
                v_addr = " ".join(filter(None, [v.address_line1, v.address_line2, v.city, v.state_code, v.pincode]))
                vendor_strings.append(f"{v.legal_name} {v_addr}".strip())

            # Create query string
            query_addr = address or ""
            query_string = f"{name} {query_addr}".strip()

            # Use rapidfuzz for best match
            matches = process.extract(query_string, vendor_strings, scorer=fuzz.token_sort_ratio, limit=5)

            candidates = []
            for _, score, idx in matches:
                vendor = vendors[idx]
                v_addr = " ".join(
                    filter(
                        None,
                        [vendor.address_line1, vendor.address_line2, vendor.city, vendor.state_code, vendor.pincode],
                    )
                )

                # Also check individual name and address scores
                name_score = fuzz.ratio(name.upper(), vendor.legal_name.upper())
                addr_score = fuzz.token_sort_ratio(query_addr.upper(), v_addr.upper()) if query_addr and v_addr else 0

                combined_score = (score * 0.6) + (name_score * 0.3) + (addr_score * 0.1)

                candidates.append(
                    {
                        "vendor_id": vendor.id,
                        "vendor_gstin": vendor.gstin,
                        "vendor_name": vendor.legal_name,
                        "combined_score": combined_score,
                        "name_score": name_score,
                        "address_score": addr_score,
                    }
                )

            # Filter by threshold
            good_candidates = [c for c in candidates if c["combined_score"] >= VENDOR_NAME_THRESHOLD]

            if good_candidates:
                best = max(good_candidates, key=lambda c: c["combined_score"])
                return VendorMatchResult(
                    vendor_id=best["vendor_id"],
                    vendor_gstin=best["vendor_gstin"],
                    vendor_name=best["vendor_name"],
                    match_type="fuzzy_name_address",
                    confidence=best["combined_score"] / 100.0,
                    candidates=good_candidates[:3],
                )

            # Return best even if below threshold (for review)
            if candidates:
                best = max(candidates, key=lambda c: c["combined_score"])
                return VendorMatchResult(
                    vendor_id=best["vendor_id"],
                    vendor_gstin=best["vendor_gstin"],
                    vendor_name=best["vendor_name"],
                    match_type="fuzzy_name_address_low_confidence",
                    confidence=best["combined_score"] / 100.0,
                    candidates=candidates[:3],
                )

    return VendorMatchResult(vendor_id=None, vendor_gstin=gstin, vendor_name=name, match_type="none", confidence=0.0)


async def resolve_po(
    invoice_vendor_gstin: str,
    invoice_number: str,
    invoice_date: str,
    invoice_amount: Decimal,
    invoice_lines: list[dict],
    session=None,
) -> list[POCandidate]:
    """Resolve PO from invoice data.

    Priority:
    1. Explicit PO reference on invoice
    2. Ranked candidates from vendor + amount + date + item similarity
    """
    if session is None:
        async with get_session() as session:
            return await _resolve_po(
                session, invoice_vendor_gstin, invoice_number, invoice_date, invoice_amount, invoice_lines
            )
    else:
        return await _resolve_po(
            session, invoice_vendor_gstin, invoice_number, invoice_date, invoice_amount, invoice_lines
        )


async def _resolve_po(
    session,
    invoice_vendor_gstin: str,
    invoice_number: str,
    invoice_date: str,
    invoice_amount: Decimal,
    invoice_lines: list[dict],
) -> list[POCandidate]:
    """Internal PO resolution."""
    from sqlalchemy import select

    # Get vendor ID from GSTIN
    vendor_result = await session.execute(
        select(Vendor).where(Vendor.gstin == invoice_vendor_gstin, Vendor.is_active == True)
    )
    vendor = vendor_result.scalar_one_or_none()

    if not vendor:
        return []

    # Get all open POs for this vendor
    result = await session.execute(
        select(PurchaseOrder).where(PurchaseOrder.vendor_id == vendor.id, PurchaseOrder.status.in_(["open", "partial"]))
    )
    pos = result.scalars().all()

    if not pos:
        return []

    candidates = []
    for po in pos:
        score = 0.0
        reasons = []

        # Amount similarity (40% weight)
        if po.grand_total > 0:
            amount_diff_pct = float(abs(po.grand_total - invoice_amount) / invoice_amount * 100)
            if amount_diff_pct <= PO_AMOUNT_THRESHOLD:
                score += 40
                reasons.append(f"Amount match ({amount_diff_pct:.1f}% diff)")
            elif amount_diff_pct <= 20:
                score += 20 * (1 - amount_diff_pct / 20)
                reasons.append(f"Amount close ({amount_diff_pct:.1f}% diff)")

        # Date proximity (20% weight)
        from datetime import datetime

        try:
            po_date = po.po_date
            inv_date = datetime.strptime(invoice_date[:10], "%Y-%m-%d").date()
            days_diff = abs((inv_date - po_date).days)
            if days_diff <= 7:
                score += 20
                reasons.append(f"Date match ({days_diff} days)")
            elif days_diff <= PO_DATE_WINDOW_DAYS:
                score += 10 * (1 - days_diff / PO_DATE_WINDOW_DAYS)
                reasons.append(f"Date close ({days_diff} days)")
        except (ValueError, TypeError):
            pass

        # Item similarity (30% weight)
        if invoice_lines:
            # Get PO lines
            from sqlalchemy import select

            from ..db.models import POLine

            po_lines_result = await session.execute(select(POLine).where(POLine.po_id == po.id))
            po_lines = po_lines_result.scalars().all()

            if po_lines:
                item_scores = []
                for inv_line in invoice_lines:
                    inv_desc = inv_line.get("item_description", "").lower()
                    inv_hsn = inv_line.get("hsn_code", "")

                    best_match = 0
                    for po_line in po_lines:
                        po_desc = po_line.item_description.lower()
                        po_hsn = po_line.hsn_code

                        # HSN match (high weight)
                        if inv_hsn and inv_hsn == po_hsn:
                            best_match = max(best_match, 90)

                        # Description fuzzy match
                        desc_score = fuzz.token_sort_ratio(inv_desc, po_desc)
                        best_match = max(best_match, desc_score)

                    item_scores.append(best_match)

                avg_item_score = sum(item_scores) / len(item_scores) if item_scores else 0
                score += avg_item_score * 0.3
                if avg_item_score > 70:
                    reasons.append(f"Items match ({avg_item_score:.0f}%)")

        # PO reference on invoice (10% weight if present)
        # This would be checked separately

        candidates.append(
            POCandidate(
                po_id=po.id,
                po_number=po.po_number,
                vendor_gstin=vendor.gstin,
                vendor_name=vendor.legal_name,
                po_date=str(po.po_date),
                grand_total=po.grand_total,
                score=score,
                match_reasons=reasons,
            )
        )

    # Sort by score descending
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


# Synchronous versions for testing
def resolve_vendor_sync(gstin: str | None, name: str | None, address: str | None) -> VendorMatchResult:
    import asyncio

    return asyncio.run(resolve_vendor(gstin, name, address))


def resolve_po_sync(
    invoice_vendor_gstin: str,
    invoice_number: str,
    invoice_date: str,
    invoice_amount: Decimal,
    invoice_lines: list[dict],
) -> list[POCandidate]:
    import asyncio

    return asyncio.run(resolve_po(invoice_vendor_gstin, invoice_number, invoice_date, invoice_amount, invoice_lines))


