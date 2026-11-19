"""V7: Invoice date plausibility and not before PO date."""

from dataclasses import dataclass
from datetime import date, datetime

from ..db.models import Invoice, PurchaseOrder


@dataclass
class ValidationResult:
    """Result of a validation check."""

    passed: bool
    message: str
    details: dict | None = None


def parse_date(date_str: str) -> date | None:
    """Parse date from various formats."""
    formats = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d"]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def validate_invoice_date_plausibility(invoice_date: str) -> ValidationResult:
    """V7a: Validate invoice date is plausible (not future, not too old)."""
    inv_date = parse_date(invoice_date)
    if inv_date is None:
        return ValidationResult(False, f"Cannot parse date: {invoice_date}")

    today = date.today()

    # Not in future (allow 1 day buffer for timezone)
    if inv_date > today:
        return ValidationResult(
            False,
            f"Invoice date {inv_date} is in the future (today: {today})",
            {"invoice_date": str(inv_date), "today": str(today)},
        )

    # Not too old (> 10 years)
    if (today - inv_date).days > 3650:
        return ValidationResult(
            False,
            f"Invoice date {inv_date} is very old (>{3650} days)",
            {"invoice_date": str(inv_date), "today": str(today), "days_old": (today - inv_date).days},
        )

    return ValidationResult(
        True, f"Invoice date {inv_date} is plausible", {"invoice_date": str(inv_date), "today": str(today)}
    )


def validate_invoice_not_before_po(invoice_date: str, po_date: str) -> ValidationResult:
    """V7b: Validate invoice date is not before PO date."""
    inv_date = parse_date(invoice_date)
    po_dt = parse_date(po_date)

    if inv_date is None:
        return ValidationResult(False, f"Cannot parse invoice date: {invoice_date}")
    if po_dt is None:
        return ValidationResult(False, f"Cannot parse PO date: {po_date}")

    if inv_date < po_dt:
        return ValidationResult(
            False,
            f"Invoice date {inv_date} is before PO date {po_dt}",
            {"invoice_date": str(inv_date), "po_date": str(po_dt)},
        )

    return ValidationResult(
        True,
        f"Invoice date {inv_date} is on/after PO date {po_dt}",
        {"invoice_date": str(inv_date), "po_date": str(po_dt)},
    )


def validate_due_date(invoice_date: str, due_date: str) -> ValidationResult:
    """Validate due date is after invoice date."""
    inv_date = parse_date(invoice_date)
    due_dt = parse_date(due_date)

    if inv_date is None or due_dt is None:
        return ValidationResult(False, "Cannot parse dates")

    if due_dt < inv_date:
        return ValidationResult(
            False,
            f"Due date {due_dt} is before invoice date {inv_date}",
            {"invoice_date": str(inv_date), "due_date": str(due_dt)},
        )

    # Due date typically within 90 days
    if (due_dt - inv_date).days > 90:
        return ValidationResult(
            False,
            f"Due date {due_dt} is >90 days after invoice date {inv_date}",
            {"invoice_date": str(inv_date), "due_date": str(due_dt), "days_diff": (due_dt - inv_date).days},
        )

    return ValidationResult(
        True, f"Due date {due_dt} is valid", {"invoice_date": str(inv_date), "due_date": str(due_dt)}
    )


def validate_grn_date(grn_date: str, po_date: str) -> ValidationResult:
    """Validate GRN date is after PO date."""
    grn_dt = parse_date(grn_date)
    po_dt = parse_date(po_date)

    if grn_dt is None or po_dt is None:
        return ValidationResult(False, "Cannot parse dates")

    if grn_dt < po_dt:
        return ValidationResult(
            False, f"GRN date {grn_dt} is before PO date {po_dt}", {"grn_date": str(grn_dt), "po_date": str(po_dt)}
        )

    return ValidationResult(True, f"GRN date {grn_dt} is valid", {"grn_date": str(grn_dt), "po_date": str(po_dt)})


def validate_all_dates(invoice: Invoice, po: PurchaseOrder | None = None) -> list[ValidationResult]:
    """Run all date validations for an invoice."""
    results = []

    # V7a: Invoice date plausibility
    results.append(validate_invoice_date_plausibility(str(invoice.invoice_date)))

    # V7b: Invoice date not before PO date
    if po:
        results.append(validate_invoice_not_before_po(str(invoice.invoice_date), str(po.po_date)))

    # Due date validation
    if invoice.due_date:
        results.append(validate_due_date(str(invoice.invoice_date), str(invoice.due_date)))

    return results
