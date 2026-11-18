"""Oracle baseline evaluation.

Runs downstream decision logic on ground-truth fields to get an upper bound
performance. This separates extraction errors from logic errors.
"""

import argparse
import json
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from datagen.models import (
    Decision,
    DefectType,
    GroundTruth,
    TaxType,
)

from .harness import write_results

# Tolerance configuration (matching M3 spec)
PRICE_TOLERANCE_PCT = Decimal("0.05")  # 5%
QUANTITY_TOLERANCE_ABS = Decimal("0.02")  # 2%


def validate_gstin(gstin: str) -> bool:
    """Validate GSTIN checksum (simplified)."""
    if not gstin or len(gstin) != 15:
        return False
    # Full validation in datagen.gstin
    return True


def validate_tax_arithmetic(invoice: GroundTruth) -> list[str]:
    """Validate tax arithmetic on ground truth."""
    errors = []

    # Check line totals
    for line in invoice.lines:
        qty = Decimal(line["quantity"])
        price = Decimal(line["unit_price"])
        disc = Decimal(line.get("discount_percent", "0"))
        tax_rate = Decimal(line["tax_rate"])

        taxable = qty * price * (Decimal("1") - disc / Decimal("100"))
        tax_amt = taxable * tax_rate
        line_total = taxable + tax_amt

        gt_taxable = Decimal(line["taxable_value"])
        gt_tax = Decimal(line["tax_amount"])
        gt_total = Decimal(line["line_total"])

        if abs(taxable - gt_taxable) > Decimal("0.01"):
            errors.append(f"Line {line['line_number']}: taxable value mismatch {taxable} vs {gt_taxable}")
        if abs(tax_amt - gt_tax) > Decimal("0.01"):
            errors.append(f"Line {line['line_number']}: tax amount mismatch {tax_amt} vs {gt_tax}")
        if abs(line_total - gt_total) > Decimal("0.01"):
            errors.append(f"Line {line['line_number']}: line total mismatch {line_total} vs {gt_total}")

    # Check totals
    subtotal = sum(Decimal(l["taxable_value"]) for l in invoice.lines)
    total_tax = sum(Decimal(l["tax_amount"]) for l in invoice.lines)
    grand_total = subtotal + total_tax

    if abs(subtotal - Decimal(invoice.totals["subtotal"])) > Decimal("0.01"):
        errors.append(f"Subtotal mismatch: {subtotal} vs {invoice.totals['subtotal']}")
    if abs(total_tax - Decimal(invoice.totals["total_tax"])) > Decimal("0.01"):
        errors.append(f"Total tax mismatch: {total_tax} vs {invoice.totals['total_tax']}")
    if abs(grand_total - Decimal(invoice.totals["grand_total"])) > Decimal("0.01"):
        errors.append(f"Grand total mismatch: {grand_total} vs {invoice.totals['grand_total']}")

    return errors


def validate_gst_rules(invoice: GroundTruth) -> list[str]:
    """Validate GST rules (tax type vs place of supply)."""
    errors = []

    place_of_supply = invoice.header.get("place_of_supply", "")
    place_of_delivery = invoice.header.get("place_of_delivery", "")

    is_interstate = place_of_supply != place_of_delivery

    for line in invoice.lines:
        tax_type = line["tax_type"]

        if is_interstate:
            # Should be IGST
            if tax_type != TaxType.IGST.value:
                errors.append(f"Line {line['line_number']}: Interstate supply should use IGST, got {tax_type}")
        else:
            # Should be CGST + SGST
            if tax_type == TaxType.IGST.value:
                errors.append(f"Line {line['line_number']}: Intrastate supply should use CGST+SGST, got IGST")

    return errors


def validate_duplicate(invoice: GroundTruth, seen_invoices: dict[str, str]) -> list[str]:
    """Check for exact duplicates (D05)."""
    errors = []

    key = (
        invoice.vendor_gstin,
        invoice.header.get("invoice_date", "")[:4],  # Financial year
        "INV",  # doc type
        invoice.invoice_number,
    )
    key_str = "|".join(key)

    if key_str in seen_invoices:
        errors.append(f"Exact duplicate: same vendor GSTIN + FY + type + number as {seen_invoices[key_str]}")
    else:
        seen_invoices[key_str] = invoice.invoice_number

    return errors


def validate_near_duplicate(invoice: GroundTruth, seen_invoices: list[GroundTruth]) -> list[str]:
    """Check for near duplicates (D06)."""
    errors = []

    for other in seen_invoices:
        if other.invoice_number == invoice.invoice_number:
            continue

        # Same vendor, similar amount, close date
        if other.vendor_gstin == invoice.vendor_gstin:
            amt1 = Decimal(invoice.totals["grand_total"])
            amt2 = Decimal(other.totals["grand_total"])

            if amt1 == amt2:
                # Same amount - check date proximity
                try:
                    date1 = date.fromisoformat(invoice.header["invoice_date"])
                    date2 = date.fromisoformat(other.header["invoice_date"])
                    if abs((date1 - date2).days) <= 30:
                        errors.append(f"Near duplicate: same vendor + amount, date diff {(date1 - date2).days} days")
                except (ValueError, KeyError):
                    pass

    return errors


def validate_bank_details(invoice: GroundTruth, vendor_master: dict[str, str]) -> list[str]:
    """Validate bank details against vendor master (D10)."""
    errors = []

    # In ground truth, we don't have bank details directly
    # This would check against vendor master in real implementation
    # For oracle, we check if defect D10 is present
    for defect in invoice.defects:
        if defect.type == DefectType.D10:
            errors.append("Bank detail change detected (D10)")

    return errors


def validate_po_reference(invoice: GroundTruth) -> list[str]:
    """Validate PO reference (D11)."""
    errors = []

    po_ref = invoice.header.get("po_reference")
    if not po_ref:
        # Check if this should have a PO
        for defect in invoice.defects:
            if defect.type == DefectType.D11:
                errors.append("Missing or wrong PO reference (D11)")

    return errors


def validate_edited_amount(invoice: GroundTruth) -> list[str]:
    """Detect edited amounts (D12)."""
    errors = []

    for defect in invoice.defects:
        if defect.type == DefectType.D12:
            errors.append("Edited amount detected (D12)")

    return errors


def validate_embedded_instruction(invoice: GroundTruth) -> list[str]:
    """Detect embedded instructions (D13)."""
    errors = []

    for defect in invoice.defects:
        if defect.type == DefectType.D13:
            errors.append("Embedded instruction detected (D13)")

    return errors


def validate_illegible(invoice: GroundTruth) -> list[str]:
    """Check for illegible documents (D14)."""
    errors = []

    for defect in invoice.defects:
        if defect.type == DefectType.D14:
            errors.append("Illegible or not an invoice (D14)")

    return errors


def validate_policy(invoice: GroundTruth) -> list[str]:
    """Check policy violations (D15)."""
    errors = []

    for defect in invoice.defects:
        if defect.type == DefectType.D15:
            errors.append("Policy violation (D15)")

    return errors


def decide_invoice(
    invoice: GroundTruth,
    seen_invoices: dict[str, str],
    seen_list: list[GroundTruth],
    vendor_master: dict[str, str],
) -> Decision:
    """Run decision logic on ground truth invoice.

    Returns the expected decision based on validators and defects.
    """
    all_errors = []

    # Run all validators
    all_errors.extend(validate_tax_arithmetic(invoice))
    all_errors.extend(validate_gst_rules(invoice))
    all_errors.extend(validate_duplicate(invoice, seen_invoices))
    all_errors.extend(validate_near_duplicate(invoice, seen_list))
    all_errors.extend(validate_bank_details(invoice, vendor_master))
    all_errors.extend(validate_po_reference(invoice))
    all_errors.extend(validate_edited_amount(invoice))
    all_errors.extend(validate_embedded_instruction(invoice))
    all_errors.extend(validate_illegible(invoice))
    all_errors.extend(validate_policy(invoice))

    # Determine decision based on defects present
    defect_types = {d.type for d in invoice.defects}

    # Clean - no defects
    if defect_types == {DefectType.D01}:
        return Decision.POST

    # Reject conditions
    if DefectType.D05 in defect_types:  # Exact duplicate
        return Decision.REJECT
    if DefectType.D14 in defect_types:  # Illegible
        return Decision.REJECT

    # Escalate conditions
    if DefectType.D06 in defect_types:  # Near duplicate
        return Decision.ESCALATE
    if DefectType.D09 in defect_types:  # Invalid GSTIN
        return Decision.ESCALATE
    if DefectType.D10 in defect_types:  # Bank detail change
        return Decision.ESCALATE
    if DefectType.D15 in defect_types:  # Policy violation
        return Decision.ESCALATE

    # Investigate conditions (everything else)
    return Decision.INVESTIGATE


def run_oracle(
    ground_truth_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Run oracle baseline on all ground truth files."""
    gt_files = sorted(ground_truth_dir.glob("*.json"))

    seen_invoices: dict[str, str] = {}
    seen_list: list[GroundTruth] = []
    vendor_master: dict[str, str] = {}  # vendor_gstin -> bank_account_hash

    results = {
        "total": 0,
        "decisions": Counter(),
        "defect_counts": Counter(),
        "per_invoice": [],
    }

    for gt_file in gt_files:
        with open(gt_file) as f:
            data = json.load(f)

        gt = GroundTruth(**data)
        seen_list.append(gt)

        # Count defects
        for defect in gt.defects:
            results["defect_counts"][defect.type.value] += 1

        # Run decision logic
        decision = decide_invoice(gt, seen_invoices, seen_list, vendor_master)
        results["decisions"][decision.value] += 1

        # Record per-invoice result
        results["per_invoice"].append({
            "invoice_number": gt.invoice_number,
            "vendor_gstin": gt.vendor_gstin,
            "expected_decision": gt.expected_decision.value,
            "oracle_decision": decision.value,
            "match": gt.expected_decision == decision,
            "defects": [d.type.value for d in gt.defects],
        })

        results["total"] += 1

    # Summary
    results["decision_distribution"] = dict(results["decisions"])
    results["defect_distribution"] = dict(results["defect_counts"])

    # Accuracy
    matches = sum(1 for r in results["per_invoice"] if r["match"])
    results["oracle_accuracy"] = matches / results["total"] if results["total"] > 0 else 0.0


    # Write results
    _json_path, _md_path = write_results(results, output_dir, "oracle_baseline")

    return results


def main():
    parser = argparse.ArgumentParser(description="Run oracle baseline evaluation")
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=Path("data/ground_truth"),
        help="Ground truth directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/results"),
        help="Output directory",
    )

    args = parser.parse_args()

    run_oracle(args.ground_truth, args.output)


if __name__ == "__main__":
    main()
