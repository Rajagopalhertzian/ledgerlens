"""V10: Bank details vs vendor master validation."""

from dataclasses import dataclass

from ..db.database import get_session
from ..db.models import Vendor


@dataclass
class ValidationResult:
    """Result of a validation check."""

    passed: bool
    message: str
    details: dict | None = None


def normalize_account_number(acc_num: str) -> str:
    """Normalize account number for comparison."""
    return "".join(c for c in acc_num if c.isalnum())


def normalize_ifsc(ifsc: str) -> str:
    """Normalize IFSC for comparison."""
    return ifsc.strip().upper()


async def validate_bank_details(
    invoice_account_name: str | None,
    invoice_account_number: str | None,
    invoice_ifsc: str | None,
    invoice_bank_name: str | None,
    vendor_gstin: str,
    session=None,
) -> ValidationResult:
    """V10: Validate invoice bank details against vendor master."""
    if session is None:
        async with get_session() as session:
            return await _validate_bank_details(
                session, invoice_account_name, invoice_account_number, invoice_ifsc, invoice_bank_name, vendor_gstin
            )
    else:
        return await _validate_bank_details(
            session, invoice_account_name, invoice_account_number, invoice_ifsc, invoice_bank_name, vendor_gstin
        )


async def _validate_bank_details(
    session,
    invoice_account_name: str | None,
    invoice_account_number: str | None,
    invoice_ifsc: str | None,
    invoice_bank_name: str | None,
    vendor_gstin: str,
) -> ValidationResult:
    """Internal bank validation."""
    result = await session.execute(select(Vendor).where(Vendor.gstin == vendor_gstin, Vendor.is_active == True))
    vendor = result.scalar_one_or_none()

    if not vendor:
        return ValidationResult(False, f"Vendor {vendor_gstin} not found in master", {"vendor_gstin": vendor_gstin})

    mismatches = []

    # Check account name
    if invoice_account_name and vendor.bank_account_name:
        if invoice_account_name.strip().lower() != vendor.bank_account_name.strip().lower():
            mismatches.append(
                {"field": "account_name", "invoice": invoice_account_name, "master": vendor.bank_account_name}
            )

    # Check account number
    if invoice_account_number and vendor.bank_account_number:
        inv_norm = normalize_account_number(invoice_account_number)
        mast_norm = normalize_account_number(vendor.bank_account_number)
        if inv_norm != mast_norm:
            mismatches.append(
                {"field": "account_number", "invoice": invoice_account_number, "master": vendor.bank_account_number}
            )

    # Check IFSC
    if invoice_ifsc and vendor.bank_ifsc:
        inv_norm = normalize_ifsc(invoice_ifsc)
        mast_norm = normalize_ifsc(vendor.bank_ifsc)
        if inv_norm != mast_norm:
            mismatches.append({"field": "ifsc", "invoice": invoice_ifsc, "master": vendor.bank_ifsc})

    # Check bank name
    if invoice_bank_name and vendor.bank_name:
        if invoice_bank_name.strip().lower() != vendor.bank_name.strip().lower():
            mismatches.append({"field": "bank_name", "invoice": invoice_bank_name, "master": vendor.bank_name})

    if mismatches:
        return ValidationResult(
            False,
            f"Bank details mismatch: {len(mismatches)} field(s) differ",
            {
                "vendor_gstin": vendor_gstin,
                "mismatches": mismatches,
                "master_details": {
                    "account_name": vendor.bank_account_name,
                    "account_number": vendor.bank_account_number,
                    "ifsc": vendor.bank_ifsc,
                    "bank_name": vendor.bank_name,
                },
            },
        )

    return ValidationResult(True, "Bank details match vendor master", {"vendor_gstin": vendor_gstin})


def validate_bank_details_sync(
    invoice_account_name: str | None,
    invoice_account_number: str | None,
    invoice_ifsc: str | None,
    invoice_bank_name: str | None,
    vendor_gstin: str,
) -> ValidationResult:
    """Synchronous version for testing."""
    import asyncio

    return asyncio.run(
        validate_bank_details(
            invoice_account_name, invoice_account_number, invoice_ifsc, invoice_bank_name, vendor_gstin
        )
    )


from sqlalchemy import select  # noqa: E402
