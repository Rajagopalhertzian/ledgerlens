"""Three-way matching (Invoice-PO-GRN) with Hungarian algorithm."""

from decimal import Decimal

import numpy as np
from scipy.optimize import linear_sum_assignment

from ..db.models import GoodsReceipt, GRNLine, Invoice, InvoiceLine, POLine, PurchaseOrder
from .models import Discrepancy, LineMatchResult, LineMatchStatus, MatchingConfig, MatchResult, MatchStatus


def normalize_uom(qty: Decimal, from_uom: str, to_uom: str, config: MatchingConfig) -> Decimal:
    """Normalize quantity from one UoM to another."""
    if from_uom == to_uom:
        return qty

    # Check direct conversion
    if from_uom in config.uom_conversions and to_uom in config.uom_conversions[from_uom]:
        factor = config.uom_conversions[from_uom][to_uom]
        return qty * factor

    # Check reverse conversion
    if to_uom in config.uom_conversions and from_uom in config.uom_conversions[to_uom]:
        factor = config.uom_conversions[to_uom][from_uom]
        return qty / factor

    # No conversion available
    return qty


def compute_line_similarity(
    inv_line: InvoiceLine, po_line: POLine, grn_line: GRNLine | None, config: MatchingConfig
) -> float:
    """Compute similarity score between invoice line and PO/GRN lines."""
    score = 0.0

    # HSN match (high weight)
    if inv_line.hsn_code == po_line.hsn_code:
        score += 30

    # Description fuzzy match
    from rapidfuzz import fuzz

    desc_score = fuzz.token_sort_ratio(inv_line.item_description.lower(), po_line.item_description.lower())
    score += desc_score * 0.3

    # UoM match
    if inv_line.uom == po_line.uom:
        score += 10
    elif inv_line.uom in config.uom_conversions and po_line.uom in config.uom_conversions[inv_line.uom]:
        score += 5  # Convertible

    # Tax rate match
    if abs(inv_line.tax_rate - po_line.tax_rate) < Decimal("0.01"):
        score += 10

    # Tax type match
    if inv_line.tax_type == po_line.tax_type:
        score += 10

    # Quantity proximity (if GRN available)
    if grn_line:
        inv_qty_norm = normalize_uom(
            inv_line.quantity, inv_line.uom, grn_line.po_line.uom if grn_line.po_line else inv_line.uom, config
        )
        grn_qty_norm = normalize_uom(
            grn_line.quantity_accepted, grn_line.po_line.uom if grn_line.po_line else inv_line.uom, inv_line.uom, config
        )

        if inv_qty_norm > 0:
            qty_diff = float(abs(inv_qty_norm - grn_qty_norm) / inv_qty_norm * 100)
            if qty_diff <= 5:
                score += 20
            elif qty_diff <= 20:
                score += 10 * (1 - qty_diff / 20)

    # Price proximity
    inv_price_norm = inv_line.unit_price
    po_price_norm = po_line.unit_price

    # Normalize prices if UoM differs
    if inv_line.uom != po_line.uom:
        # This is a simplification - in reality we'd need price per base UoM
        pass

    if po_price_norm > 0:
        price_diff = float(abs(inv_price_norm - po_price_norm) / po_price_norm * 100)
        if price_diff <= config.price_tolerance_pct:
            score += 20
        elif price_diff <= config.price_tolerance_pct * 3:
            score += 10 * (1 - price_diff / (config.price_tolerance_pct * 3))

    return min(score, 100)


def build_cost_matrix(
    invoice_lines: list[InvoiceLine], po_lines: list[POLine], grn_lines: list[GRNLine] | None, config: MatchingConfig
) -> np.ndarray:
    """Build cost matrix for Hungarian algorithm (negative similarity for minimization)."""
    n_inv = len(invoice_lines)
    n_po = len(po_lines)

    # Create square matrix
    size = max(n_inv, n_po)
    cost_matrix = np.full((size, size), 100.0)  # High cost = low similarity

    for i, inv_line in enumerate(invoice_lines):
        for j, po_line in enumerate(po_lines):
            # Find corresponding GRN line
            grn_line = None
            if grn_lines:
                for gl in grn_lines:
                    if gl.po_line_id == po_line.id:
                        grn_line = gl
                        break

            similarity = compute_line_similarity(inv_line, po_line, grn_line, config)
            cost_matrix[i, j] = 100 - similarity  # Convert to cost

    return cost_matrix


def match_invoice_po_grn(
    invoice: Invoice, po: PurchaseOrder | None, grn: GoodsReceipt | None, config: MatchingConfig | None = None
) -> MatchResult:
    """Perform 3-way matching of invoice, PO, and GRN."""
    if config is None:
        config = MatchingConfig()

    import asyncio

    return asyncio.run(_match_invoice_po_grn_async(invoice, po, grn, config))


async def _match_invoice_po_grn_async(
    invoice: Invoice, po: PurchaseOrder | None, grn: GoodsReceipt | None, config: MatchingConfig
) -> MatchResult:
    """Async implementation of 3-way matching."""
    from sqlalchemy import select

    from ..db.database import get_session

    async with get_session() as session:
        result = MatchResult(
            invoice_id=invoice.id,
            invoice_number=invoice.invoice_number,
            po_id=po.id if po else None,
            po_number=po.po_number if po else None,
            grn_id=grn.id if grn else None,
            grn_number=grn.grn_number if grn else None,
        )

        # Get invoice lines in this session
        from ..db.models import InvoiceLine

        inv_lines_result = await session.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id))
        inv_lines = inv_lines_result.scalars().all()

        po_lines = []
        if po:
            from ..db.models import POLine

            po_result = await session.execute(select(POLine).where(POLine.po_id == po.id))
            po_lines = po_result.scalars().all()

        grn_lines = []
        if grn:
            from ..db.models import GRNLine
            from sqlalchemy.orm import selectinload

            grn_result = await session.execute(
                select(GRNLine).where(GRNLine.grn_id == grn.id).options(selectinload(GRNLine.po_line))
            )
            grn_lines = grn_result.scalars().all()

    # Build GRN line lookup by PO line ID
    grn_by_po_line = {gl.po_line_id: gl for gl in grn_lines}

    # If no PO or no GRN, mark accordingly
    if not po:
        result.status = MatchStatus.MISSING_PO
        for inv_line in inv_lines:
            result.line_matches.append(
                LineMatchResult(
                    invoice_line_id=inv_line.id,
                    invoice_line_number=inv_line.line_number,
                    status=LineMatchStatus.MISSING_IN_PO,
                )
            )
        result.missing_in_po = len(inv_lines)
        return result

    if not grn and config.require_grn:
        result.status = MatchStatus.MISSING_GRN

    # Build cost matrix for Hungarian algorithm
    if inv_lines and po_lines:
        cost_matrix = np.full((len(inv_lines), len(po_lines)), 100.0)

        for i, inv_line in enumerate(inv_lines):
            for j, po_line in enumerate(po_lines):
                grn_line = grn_by_po_line.get(po_line.id)
                similarity = compute_line_similarity(inv_line, po_line, grn_line, config)
                cost_matrix[i, j] = 100 - similarity

        # Apply Hungarian algorithm
        row_indices, col_indices = linear_sum_assignment(cost_matrix)

        matched_po_lines = set()

        for row_idx, col_idx in zip(row_indices, col_indices):
            inv_line = inv_lines[row_idx]
            po_line = po_lines[col_idx]
            grn_line = grn_by_po_line.get(po_line.id)

            cost = float(cost_matrix[row_idx, col_idx])
            similarity = 100.0 - cost

            matched_po_lines.add(po_line.id)

            # Determine match status
            line_result = _evaluate_line_match(inv_line, po_line, grn_line, similarity, config)
            result.line_matches.append(line_result)

        # Handle unmatched invoice lines (extra in invoice)
        for i, inv_line in enumerate(inv_lines):
            if not any(lm.invoice_line_id == inv_line.id for lm in result.line_matches):
                result.line_matches.append(
                    LineMatchResult(
                        invoice_line_id=inv_line.id,
                        invoice_line_number=inv_line.line_number,
                        status=LineMatchStatus.EXTRA_IN_INVOICE,
                    )
                )
                result.extra_in_invoice += 1

        # Handle unmatched PO lines (missing in invoice)
        for po_line in po_lines:
            if po_line.id not in matched_po_lines:
                result.line_matches.append(
                    LineMatchResult(
                        invoice_line_id=None,
                        invoice_line_number=None,
                        po_line_id=po_line.id,
                        po_line_number=po_line.line_number,
                        status=LineMatchStatus.MISSING_IN_INVOICE,
                    )
                )
                result.missing_in_po += 1

    # Calculate summary
    _calculate_summary(result, invoice, po, grn, config)

    # Determine overall status
    _determine_overall_status(result)

    return result


def _evaluate_line_match(
    inv_line: InvoiceLine, po_line: POLine, grn_line: GRNLine | None, similarity: float, config: MatchingConfig
) -> LineMatchResult:
    """Evaluate a single line match."""
    discrepancies = []

    # Quantity comparison
    inv_qty = inv_line.quantity
    grn_qty = grn_line.quantity_accepted if grn_line else None

    # Normalize quantities
    grn_po_line_uom = grn_line.po_line.uom if grn_line and grn_line.po_line else inv_line.uom
    if grn_line and inv_line.uom != grn_po_line_uom:
        inv_qty_norm = normalize_uom(inv_qty, inv_line.uom, grn_po_line_uom, config)
        grn_qty_norm = normalize_uom(grn_qty, grn_po_line_uom, inv_line.uom, config) if grn_qty is not None else None
    else:
        inv_qty_norm = inv_qty
        grn_qty_norm = grn_qty

    # Price comparison
    price_diff_pct = None
    if po_line.unit_price > 0:
        price_diff_pct = float(abs(inv_line.unit_price - po_line.unit_price) / po_line.unit_price * 100)

    # Determine status
    if similarity >= 90:
        status = LineMatchStatus.MATCHED
    elif similarity >= 70:
        status = LineMatchStatus.PARTIAL
    else:
        status = LineMatchStatus.MISMATCH

    # Add specific discrepancies
    if price_diff_pct is not None and price_diff_pct > config.price_tolerance_pct:
        discrepancies.append(
            Discrepancy(
                field="unit_price",
                invoice_value=str(inv_line.unit_price),
                po_value=str(po_line.unit_price),
                difference=f"{price_diff_pct:.2f}%",
                tolerance=f"{config.price_tolerance_pct}%",
                severity="high" if price_diff_pct > config.price_tolerance_pct * 2 else "medium",
            )
        )
        status = LineMatchStatus.PRICE_MISMATCH

    if grn_qty_norm is not None:
        qty_diff = abs(inv_qty_norm - grn_qty_norm)
        if qty_diff > config.quantity_tolerance_abs:
            discrepancies.append(
                Discrepancy(
                    field="quantity",
                    invoice_value=str(inv_qty),
                    grn_value=str(grn_qty),
                    difference=str(qty_diff),
                    tolerance=str(config.quantity_tolerance_abs),
                    severity="high" if qty_diff > config.quantity_tolerance_abs * 5 else "medium",
                )
            )
            status = LineMatchStatus.QUANTITY_MISMATCH

    # Tax rate check
    if abs(inv_line.tax_rate - po_line.tax_rate) > Decimal("0.01"):
        discrepancies.append(
            Discrepancy(
                field="tax_rate",
                invoice_value=str(inv_line.tax_rate),
                po_value=str(po_line.tax_rate),
                severity="medium",
            )
        )
        status = LineMatchStatus.TAX_MISMATCH

    # Tax type check
    if inv_line.tax_type != po_line.tax_type:
        discrepancies.append(
            Discrepancy(
                field="tax_type",
                invoice_value=inv_line.tax_type.value,
                po_value=po_line.tax_type.value,
                severity="high",
            )
        )
        status = LineMatchStatus.TAX_MISMATCH

    if not grn_line:
        status = LineMatchStatus.MISSING_IN_GRN

    return LineMatchResult(
        invoice_line_id=inv_line.id,
        invoice_line_number=inv_line.line_number,
        po_line_id=po_line.id,
        po_line_number=po_line.line_number,
        grn_line_id=grn_line.id if grn_line else None,
        grn_line_number=grn_line.line_number if grn_line else None,
        status=status,
        discrepancies=discrepancies,
        invoice_qty=inv_line.quantity,
        po_qty=po_line.quantity,
        grn_qty=grn_line.quantity_accepted if grn_line else None,
        invoice_price=inv_line.unit_price,
        po_price=po_line.unit_price,
        price_diff_pct=price_diff_pct,
        invoice_tax_rate=inv_line.tax_rate,
        po_tax_rate=po_line.tax_rate,
        tax_type_match=(inv_line.tax_type == po_line.tax_type),
    )


def _calculate_summary(
    result: MatchResult, invoice: Invoice, po: PurchaseOrder | None, grn: GoodsReceipt | None, config: MatchingConfig
) -> None:
    """Calculate summary totals."""
    result.total_lines = len(result.line_matches)

    for lm in result.line_matches:
        if lm.status == LineMatchStatus.MATCHED:
            result.matched_lines += 1
        elif lm.status == LineMatchStatus.PARTIAL:
            result.partial_lines += 1
        elif lm.status in (
            LineMatchStatus.QUANTITY_MISMATCH,
            LineMatchStatus.PRICE_MISMATCH,
            LineMatchStatus.TAX_MISMATCH,
        ):
            result.mismatched_lines += 1
        elif lm.status == LineMatchStatus.MISSING_IN_GRN:
            result.missing_in_grn += 1
        elif lm.status == LineMatchStatus.MISSING_IN_PO:
            result.missing_in_po += 1
        elif lm.status == LineMatchStatus.EXTRA_IN_INVOICE:
            result.extra_in_invoice += 1

        # Collect discrepancies
        result.discrepancies.extend(lm.discrepancies)

    # Totals comparison
    result.invoice_subtotal = invoice.subtotal
    result.invoice_tax = invoice.total_tax
    result.invoice_total = invoice.grand_total

    if po:
        result.po_subtotal = po.subtotal
        result.po_tax = po.total_tax
        result.po_total = po.grand_total

        if invoice.subtotal and po.subtotal and po.subtotal > 0:
            result.subtotal_diff_pct = float(abs(invoice.subtotal - po.subtotal) / po.subtotal * 100)

        if invoice.total_tax and po.total_tax and po.total_tax > 0:
            result.tax_diff_pct = float(abs(invoice.total_tax - po.total_tax) / po.total_tax * 100)

        if invoice.grand_total and po.grand_total and po.grand_total > 0:
            result.total_diff_pct = float(abs(invoice.grand_total - po.grand_total) / po.grand_total * 100)

    if grn:
        # GRN doesn't have totals directly - would need to compute from lines
        pass


def _determine_overall_status(result: MatchResult) -> None:
    """Determine overall match status."""
    if result.missing_in_po > 0 and result.missing_in_grn > 0:
        result.status = MatchStatus.MISMATCH
    elif result.missing_in_po > 0:
        result.status = MatchStatus.MISSING_PO
    elif result.missing_in_grn > 0 and result.total_lines > 0:
        result.status = MatchStatus.MISSING_GRN
    elif result.mismatched_lines > 0:
        result.status = MatchStatus.MISMATCH
    elif result.partial_lines > 0 or result.extra_in_invoice > 0:
        result.status = MatchStatus.PARTIAL
    elif result.matched_lines == result.total_lines and result.total_lines > 0:
        result.status = MatchStatus.MATCHED
    else:
        result.status = MatchStatus.MISMATCH
