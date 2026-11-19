"""V6: IRN recomputation per e-invoice spec."""

import hashlib
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """Result of a validation check."""

    passed: bool
    message: str
    details: dict | None = None


def compute_irn(supplier_gstin: str, doc_type: str, doc_number: str, fin_year: str) -> str:
    """Compute IRN per e-invoice specification.

    IRN = SHA-256(supplier_gstin + doc_type + doc_number + fin_year)
    Returns 64-character hex string.
    """
    # Normalize inputs
    supplier_gstin = supplier_gstin.strip().upper()
    doc_type = doc_type.strip().upper()
    doc_number = doc_number.strip().upper()
    fin_year = fin_year.strip().upper()

    # Concatenate as per spec
    payload = f"{supplier_gstin}{doc_type}{doc_number}{fin_year}"

    # SHA-256 hash
    irn = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return irn


def validate_irn(irn: str, supplier_gstin: str, doc_type: str, doc_number: str, fin_year: str) -> ValidationResult:
    """V6: Validate IRN by recomputing and comparing."""
    if not irn:
        return ValidationResult(False, "IRN is empty")

    if len(irn) != 64:
        return ValidationResult(
            False, f"IRN must be 64 hex characters, got {len(irn)}", {"irn": irn, "length": len(irn)}
        )

    # Try to parse as hex
    try:
        int(irn, 16)
    except ValueError:
        return ValidationResult(False, "IRN is not valid hex", {"irn": irn})

    # Recompute
    expected_irn = compute_irn(supplier_gstin, doc_type, doc_number, fin_year)

    passed = irn.lower() == expected_irn.lower()

    return ValidationResult(
        passed,
        f"IRN {'matches' if passed else 'MISMATCH'} recomputed value",
        {
            "provided_irn": irn,
            "computed_irn": expected_irn,
            "supplier_gstin": supplier_gstin,
            "doc_type": doc_type,
            "doc_number": doc_number,
            "fin_year": fin_year,
        },
    )


def extract_fin_year(invoice_date: str) -> str:
    """Extract financial year from invoice date (YYYY-MM-DD).

    Indian financial year: April 1 - March 31
    Format: YYYY-YY (e.g., 2024-25 for FY 2024-25)
    """
    from datetime import datetime

    try:
        date_obj = datetime.strptime(invoice_date[:10], "%Y-%m-%d")
        year = date_obj.year
        month = date_obj.month

        if month >= 4:  # April onwards
            return f"{year}-{str(year + 1)[2:]}"
        else:  # Jan-Mar
            return f"{year - 1}-{str(year)[2:]}"
    except ValueError:
        # Default to current FY if parsing fails
        from datetime import date

        today = date.today()
        year = today.year
        if today.month >= 4:
            return f"{year}-{str(year + 1)[2:]}"
        return f"{year - 1}-{str(year)[2:]}"


def validate_irn_from_invoice(
    irn: str, supplier_gstin: str, invoice_number: str, invoice_date: str, doc_type: str = "INV"
) -> ValidationResult:
    """Validate IRN using invoice data."""
    fin_year = extract_fin_year(invoice_date)
    return validate_irn(irn, supplier_gstin, doc_type, invoice_number, fin_year)
