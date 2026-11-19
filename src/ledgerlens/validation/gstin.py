"""V1: GSTIN format and checksum validation.
V2: GSTIN matches vendor master validation.
"""

import re
from dataclasses import dataclass

from ..db.database import get_session
from ..db.models import Vendor

# GSTIN format: 2-digit state + 5-letter PAN + 4-digit PAN + 1-letter PAN + 1-char entity + Z + 1-char checksum
GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[A-Z0-9]{1}Z[A-Z0-9]{1}$")

# Valid state codes (01-38, 97, 99)
VALID_STATE_CODES = {
    "01",
    "02",
    "03",
    "04",
    "05",
    "06",
    "07",
    "08",
    "09",
    "10",
    "11",
    "12",
    "13",
    "14",
    "15",
    "16",
    "17",
    "18",
    "19",
    "20",
    "21",
    "22",
    "23",
    "24",
    "25",
    "26",
    "27",
    "28",
    "29",
    "30",
    "31",
    "32",
    "33",
    "34",
    "35",
    "36",
    "37",
    "38",
    "97",
    "99",
}

# GSTIN checksum character set
CHECKSUM_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
WEIGHTS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]


@dataclass
class ValidationResult:
    """Result of a validation check."""

    passed: bool
    message: str
    details: dict | None = None


def validate_gstin_format(gstin: str) -> ValidationResult:
    """V1a: Validate GSTIN format (15 chars, valid pattern)."""
    if not gstin:
        return ValidationResult(False, "GSTIN is empty")

    gstin = gstin.strip().upper()

    if len(gstin) != 15:
        return ValidationResult(False, f"GSTIN must be 15 characters, got {len(gstin)}", {"length": len(gstin)})

    if not GSTIN_PATTERN.match(gstin):
        return ValidationResult(False, f"GSTIN format invalid: {gstin}", {"pattern": GSTIN_PATTERN.pattern})

    return ValidationResult(True, "GSTIN format valid", {"gstin": gstin})


def validate_gstin_checksum(gstin: str) -> ValidationResult:
    """V1b: Validate GSTIN checksum using official algorithm."""
    if not gstin or len(gstin) != 15:
        return ValidationResult(False, "GSTIN must be 15 characters for checksum validation")

    gstin = gstin.strip().upper()

    try:
        total = 0
        for i, ch in enumerate(gstin[:14]):
            val = CHECKSUM_CHARS.index(ch)
            total += val * WEIGHTS[i]

        check_val = (36 - (total % 36)) % 36
        expected_check = CHECKSUM_CHARS[check_val]

        passed = gstin[14] == expected_check
        return ValidationResult(
            passed,
            f"GSTIN checksum {'valid' if passed else 'INVALID'}",
            {
                "gstin": gstin,
                "expected_checksum": expected_check,
                "actual_checksum": gstin[14],
                "calculated_value": check_val,
            },
        )
    except (ValueError, IndexError) as e:
        return ValidationResult(False, f"Checksum calculation error: {e}")


def validate_state_code(gstin: str) -> ValidationResult:
    """Validate GSTIN state code."""
    if not gstin or len(gstin) < 2:
        return ValidationResult(False, "GSTIN too short for state code")

    state_code = gstin[:2]
    passed = state_code in VALID_STATE_CODES
    return ValidationResult(
        passed,
        f"State code {'valid' if passed else 'invalid'}: {state_code}",
        {"state_code": state_code, "valid_codes": sorted(VALID_STATE_CODES)},
    )


def validate_gstin_full(gstin: str) -> list[ValidationResult]:
    """Run all V1 validations on a GSTIN."""
    results = []
    results.append(validate_gstin_format(gstin))
    results.append(validate_gstin_checksum(gstin))
    results.append(validate_state_code(gstin))
    return results


async def validate_gstin_vendor_match(gstin: str, vendor_name: str | None = None, session=None) -> ValidationResult:
    """V2: Validate GSTIN matches vendor master data.

    Args:
        gstin: The GSTIN to validate
        vendor_name: Optional vendor name for fuzzy matching
        session: Optional database session (creates one if not provided)
    """
    if not gstin:
        return ValidationResult(False, "GSTIN is empty")

    gstin = gstin.strip().upper()

    # Use provided session or create new one
    if session is None:
        async with get_session() as session:
            return await _check_vendor_master(session, gstin, vendor_name)
    else:
        return await _check_vendor_master(session, gstin, vendor_name)


async def _check_vendor_master(session, gstin: str, vendor_name: str | None) -> ValidationResult:
    """Check vendor master for GSTIN match."""
    result = await session.execute(select(Vendor).where(Vendor.gstin == gstin, Vendor.is_active == True))
    vendor = result.scalar_one_or_none()

    if vendor is None:
        return ValidationResult(
            False, f"GSTIN {gstin} not found in active vendor master", {"gstin": gstin, "match_type": "exact"}
        )

    # If vendor_name provided, also check fuzzy match
    if vendor_name:
        from rapidfuzz import fuzz

        name_similarity = fuzz.ratio(vendor_name.upper(), vendor.legal_name.upper()) / 100.0
        if name_similarity < 0.8:
            return ValidationResult(
                False,
                f"GSTIN matches vendor but name similarity low: {name_similarity:.2f}",
                {
                    "gstin": gstin,
                    "master_name": vendor.legal_name,
                    "provided_name": vendor_name,
                    "similarity": name_similarity,
                    "match_type": "exact_gstin_fuzzy_name",
                },
            )

    return ValidationResult(
        True,
        f"GSTIN {gstin} matches vendor: {vendor.legal_name}",
        {"gstin": gstin, "vendor_id": vendor.id, "vendor_name": vendor.legal_name, "match_type": "exact"},
    )


# For synchronous usage (e.g., in tests)
def validate_gstin_vendor_match_sync(gstin: str, vendor_name: str | None = None) -> ValidationResult:
    """Synchronous version of V2 validation (for testing)."""
    import asyncio

    return asyncio.run(validate_gstin_vendor_match(gstin, vendor_name))


from sqlalchemy import select  # noqa: E402
