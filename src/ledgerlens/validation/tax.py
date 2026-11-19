"""V3: Tax type vs places of supply validation.
V4: Tax arithmetic (line-level and total).
V5: Totals and rounding validation.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from ..db.models import GRNLine, Invoice, InvoiceLine, POLine, TaxType


@dataclass
class ValidationResult:
    """Result of a validation check."""

    passed: bool
    message: str
    details: dict | None = None


def validate_tax_type_vs_places(invoice: Invoice, lines: list[InvoiceLine]) -> list[ValidationResult]:
    """V3: Validate tax type matches places of supply/delivery.

    Intra-state (same state): CGST + SGST
    Inter-state (different states): IGST
    """
    results = []

    supply_state = invoice.place_of_supply[:2] if invoice.place_of_supply else ""
    delivery_state = invoice.place_of_delivery[:2] if invoice.place_of_delivery else ""

    intra_state = supply_state == delivery_state and supply_state != ""

    for idx, line in enumerate(lines):
        if not line.tax_type:
            results.append(ValidationResult(False, f"Line {idx}: Missing tax type", {"line_number": line.line_number}))
            continue

        tax_type = line.tax_type

        if intra_state:
            passed = tax_type in (TaxType.CGST, TaxType.SGST)
            expected = "CGST or SGST"
        else:
            passed = tax_type == TaxType.IGST
            expected = "IGST"

        results.append(
            ValidationResult(
                passed,
                f"Line {line.line_number}: {tax_type.value} for "
                f"{'intra' if intra_state else 'inter'}-state "
                f"(expected {expected})",
                {
                    "line_number": line.line_number,
                    "tax_type": tax_type.value,
                    "intra_state": intra_state,
                    "supply_state": supply_state,
                    "delivery_state": delivery_state,
                    "expected": expected,
                },
            )
        )

    return results


def validate_line_tax_arithmetic(line: InvoiceLine) -> list[ValidationResult]:
    """V4a: Validate tax arithmetic for a single line."""
    results = []

    try:
        qty = Decimal(str(line.quantity))
        price = Decimal(str(line.unit_price))
        discount = Decimal(str(line.discount_percent)) if line.discount_percent else Decimal("0")
        tax_rate = Decimal(str(line.tax_rate))

        taxable = qty * price * (Decimal("1") - discount / Decimal("100"))
        tax = taxable * tax_rate / Decimal("100")
        line_total_calc = taxable + tax

        # Check taxable value
        if line.taxable_value:
            declared_taxable = Decimal(str(line.taxable_value))
            passed = abs(taxable - declared_taxable) < Decimal("0.01")
            results.append(
                ValidationResult(
                    passed,
                    f"Line {line.line_number}: taxable {taxable.quantize(Decimal('0.01'))} "
                    f"vs declared {declared_taxable}",
                    {
                        "line_number": line.line_number,
                        "calculated": str(taxable.quantize(Decimal("0.01"))),
                        "declared": str(declared_taxable),
                        "diff": str(abs(taxable - declared_taxable).quantize(Decimal("0.01"))),
                    },
                )
            )

        # Check tax amount
        if line.tax_amount:
            declared_tax = Decimal(str(line.tax_amount))
            passed = abs(tax - declared_tax) < Decimal("0.01")
            results.append(
                ValidationResult(
                    passed,
                    f"Line {line.line_number}: tax {tax.quantize(Decimal('0.01'))} vs declared {declared_tax}",
                    {
                        "line_number": line.line_number,
                        "calculated": str(tax.quantize(Decimal("0.01"))),
                        "declared": str(declared_tax),
                        "diff": str(abs(tax - declared_tax).quantize(Decimal("0.01"))),
                    },
                )
            )

        # Check line total
        if line.line_total:
            declared_total = Decimal(str(line.line_total))
            passed = abs(line_total_calc - declared_total) < Decimal("0.01")
            results.append(
                ValidationResult(
                    passed,
                    f"Line {line.line_number}: total {line_total_calc.quantize(Decimal('0.01'))} "
                    f"vs declared {declared_total}",
                    {
                        "line_number": line.line_number,
                        "calculated": str(line_total_calc.quantize(Decimal("0.01"))),
                        "declared": str(declared_total),
                        "diff": str(abs(line_total_calc - declared_total).quantize(Decimal("0.01"))),
                    },
                )
            )

        # Check individual tax components for intra-state
        if line.tax_type in (TaxType.CGST, TaxType.SGST):
            expected_half = tax / 2
            if line.cgst_amount and line.sgst_amount:
                declared_cgst = Decimal(str(line.cgst_amount))
                declared_sgst = Decimal(str(line.sgst_amount))
                passed_cgst = abs(expected_half - declared_cgst) < Decimal("0.01")
                passed_sgst = abs(expected_half - declared_sgst) < Decimal("0.01")
                results.append(
                    ValidationResult(
                        passed_cgst and passed_sgst,
                        f"Line {line.line_number}: CGST={declared_cgst}, SGST={declared_sgst}, "
                        f"expected half={expected_half.quantize(Decimal('0.01'))}",
                        {
                            "line_number": line.line_number,
                            "expected_half": str(expected_half.quantize(Decimal("0.01"))),
                            "declared_cgst": str(declared_cgst),
                            "declared_sgst": str(declared_sgst),
                        },
                    )
                )

    except (InvalidOperation, TypeError, ValueError) as e:
        results.append(
            ValidationResult(
                False,
                f"Line {line.line_number}: Arithmetic validation error: {e}",
                {"line_number": line.line_number, "error": str(e)},
            )
        )

    return results


def validate_invoice_totals(invoice: Invoice, lines: list[InvoiceLine]) -> list[ValidationResult]:
    """V5: Validate invoice totals and rounding."""
    results = []

    try:
        # Sum line totals
        line_totals = []
        line_taxes = []
        line_taxables = []

        for line in lines:
            if line.line_total:
                line_totals.append(Decimal(str(line.line_total)))
            if line.tax_amount:
                line_taxes.append(Decimal(str(line.tax_amount)))
            if line.taxable_value:
                line_taxables.append(Decimal(str(line.taxable_value)))

        # Check subtotal (sum of taxable values)
        if line_taxables and invoice.subtotal:
            calc_subtotal = sum(line_taxables, Decimal("0"))
            declared_subtotal = Decimal(str(invoice.subtotal))
            passed = abs(calc_subtotal - declared_subtotal) < Decimal("0.01")
            results.append(
                ValidationResult(
                    passed,
                    f"Subtotal: calculated {calc_subtotal.quantize(Decimal('0.01'))} vs declared {declared_subtotal}",
                    {
                        "calculated": str(calc_subtotal.quantize(Decimal("0.01"))),
                        "declared": str(declared_subtotal),
                        "diff": str(abs(calc_subtotal - declared_subtotal).quantize(Decimal("0.01"))),
                    },
                )
            )

        # Check total tax (sum of line taxes)
        if line_taxes and invoice.total_tax:
            calc_tax = sum(line_taxes, Decimal("0"))
            declared_tax = Decimal(str(invoice.total_tax))
            passed = abs(calc_tax - declared_tax) < Decimal("0.01")
            results.append(
                ValidationResult(
                    passed,
                    f"Total tax: calculated {calc_tax.quantize(Decimal('0.01'))} vs declared {declared_tax}",
                    {
                        "calculated": str(calc_tax.quantize(Decimal("0.01"))),
                        "declared": str(declared_tax),
                        "diff": str(abs(calc_tax - declared_tax).quantize(Decimal("0.01"))),
                    },
                )
            )

        # Check grand total
        if invoice.subtotal and invoice.total_tax and invoice.grand_total:
            calc_grand = Decimal(str(invoice.subtotal)) + Decimal(str(invoice.total_tax))
            declared_grand = Decimal(str(invoice.grand_total))
            passed = abs(calc_grand - declared_grand) < Decimal("0.01")
            results.append(
                ValidationResult(
                    passed,
                    f"Grand total: {declared_grand} vs subtotal+tax {calc_grand.quantize(Decimal('0.01'))}",
                    {
                        "subtotal": str(invoice.subtotal),
                        "total_tax": str(invoice.total_tax),
                        "calculated": str(calc_grand.quantize(Decimal("0.01"))),
                        "declared": str(declared_grand),
                        "diff": str(abs(calc_grand - declared_grand).quantize(Decimal("0.01"))),
                    },
                )
            )

        # Check tax component totals (CGST, SGST, IGST, CESS)
        for tax_field, tax_name in [
            (invoice.cgst_amount, "CGST"),
            (invoice.sgst_amount, "SGST"),
            (invoice.igst_amount, "IGST"),
            (invoice.cess_amount, "CESS"),
        ]:
            if tax_field is not None:
                # Sum from lines
                line_sum = Decimal("0")
                for line in lines:
                    line_val = getattr(line, f"{tax_name.lower()}_amount", None)
                    if line_val:
                        line_sum += Decimal(str(line_val))

                declared = Decimal(str(tax_field))
                passed = abs(line_sum - declared) < Decimal("0.01")
                results.append(
                    ValidationResult(
                        passed,
                        f"{tax_name} total: line sum {line_sum.quantize(Decimal('0.01'))} vs declared {declared}",
                        {
                            "tax_type": tax_name,
                            "line_sum": str(line_sum.quantize(Decimal("0.01"))),
                            "declared": str(declared),
                            "diff": str(abs(line_sum - declared).quantize(Decimal("0.01"))),
                        },
                    )
                )

        # Check rounding (Indian rounding rules: round to nearest rupee)
        if invoice.grand_total:
            grand = Decimal(str(invoice.grand_total))
            rounded = grand.quantize(Decimal("1"), rounding="ROUND_HALF_UP")
            # In India, typically rounded to nearest rupee
            if grand != rounded:
                results.append(
                    ValidationResult(
                        False,
                        f"Grand total {grand} not rounded to nearest rupee (should be {rounded})",
                        {"grand_total": str(grand), "rounded": str(rounded)},
                    )
                )
            else:
                results.append(
                    ValidationResult(True, f"Grand total {grand} properly rounded", {"grand_total": str(grand)})
                )

    except (InvalidOperation, TypeError, ValueError) as e:
        results.append(ValidationResult(False, f"Totals validation error: {e}", {"error": str(e)}))

    return results


def validate_po_line_arithmetic(line: POLine) -> list[ValidationResult]:
    """Validate PO line arithmetic (similar to invoice)."""
    results = []

    try:
        qty = Decimal(str(line.quantity))
        price = Decimal(str(line.unit_price))
        discount = Decimal(str(line.discount_percent))
        tax_rate = Decimal(str(line.tax_rate))

        taxable = qty * price * (Decimal("1") - discount / Decimal("100"))
        tax = taxable * tax_rate / Decimal("100")
        line_total_calc = taxable + tax

        if line.taxable_value:
            declared = Decimal(str(line.taxable_value))
            passed = abs(taxable - declared) < Decimal("0.01")
            results.append(
                ValidationResult(
                    passed,
                    f"PO Line {line.line_number} taxable value",
                    {"calculated": str(taxable.quantize(Decimal("0.01"))), "declared": str(declared)},
                )
            )

        if line.tax_amount:
            declared = Decimal(str(line.tax_amount))
            passed = abs(tax - declared) < Decimal("0.01")
            results.append(
                ValidationResult(
                    passed,
                    f"PO Line {line.line_number} tax amount",
                    {"calculated": str(tax.quantize(Decimal("0.01"))), "declared": str(declared)},
                )
            )

        if line.line_total:
            declared = Decimal(str(line.line_total))
            passed = abs(line_total_calc - declared) < Decimal("0.01")
            results.append(
                ValidationResult(
                    passed,
                    f"PO Line {line.line_number} line total",
                    {"calculated": str(line_total_calc.quantize(Decimal("0.01"))), "declared": str(declared)},
                )
            )

    except (InvalidOperation, TypeError, ValueError) as e:
        results.append(ValidationResult(False, f"PO Line arithmetic error: {e}"))

    return results


def validate_grn_line_quantities(grn_line: GRNLine, po_line: POLine) -> list[ValidationResult]:
    """Validate GRN quantities against PO line."""
    results = []

    po_qty = Decimal(str(po_line.quantity))
    received = Decimal(str(grn_line.quantity_received))
    accepted = Decimal(str(grn_line.quantity_accepted))
    rejected = Decimal(str(grn_line.quantity_rejected))

    # Received should match PO quantity (or be less for partial)
    if received > po_qty:
        results.append(
            ValidationResult(
                False,
                f"GRN line {grn_line.line_number}: received {received} > PO qty {po_qty}",
                {"po_qty": str(po_qty), "received": str(received)},
            )
        )
    else:
        results.append(
            ValidationResult(
                True,
                f"GRN line {grn_line.line_number}: received {received} <= PO qty {po_qty}",
                {"po_qty": str(po_qty), "received": str(received)},
            )
        )

    # Accepted + Rejected = Received
    if accepted + rejected != received:
        results.append(
            ValidationResult(
                False,
                f"GRN line {grn_line.line_number}: accepted+rejected ({accepted + rejected}) != received ({received})",
                {"accepted": str(accepted), "rejected": str(rejected), "received": str(received)},
            )
        )
    else:
        results.append(
            ValidationResult(
                True,
                f"GRN line {grn_line.line_number}: quantities balance",
                {"accepted": str(accepted), "rejected": str(rejected), "received": str(received)},
            )
        )

    return results
