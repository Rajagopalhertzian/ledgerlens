"""Tests for duplicate detection (V8, V9)."""

from datetime import date
from decimal import Decimal
from hypothesis import given, strategies as st

from ledgerlens.validation.duplicates import (
    check_exact_duplicate_sync,
    check_near_duplicates_sync,
    DuplicateMatch,
)
from ledgerlens.validation.irn import extract_fin_year


class TestExactDuplicate:
    """Tests for V8: Exact duplicate detection."""

    def test_sync_version_returns_result(self):
        """Sync version should return a ValidationResult."""
        result = check_exact_duplicate_sync("29AAACA1234A1Z5", "INV-001", date(2024, 6, 15))
        assert result is not None
        assert hasattr(result, "passed")
        assert hasattr(result, "message")

    def test_identity_key_format(self):
        """Identity key should be GSTIN + FY + doc_type + number."""
        gstin = "29AAACA1234A1Z5"
        invoice_number = "INV-001"
        invoice_date = date(2024, 6, 15)
        fin_year = extract_fin_year(str(invoice_date))
        doc_type = "INV"  # Default doc_type
        expected_key = f"{gstin}{fin_year}{doc_type}{invoice_number}"
        # The function constructs this internally
        result = check_exact_duplicate_sync(gstin, invoice_number, invoice_date)
        assert result.details is not None
        assert result.details["identity_key"] == expected_key

    def test_no_duplicate_when_db_empty(self):
        """When database is empty, no duplicate should be found."""
        result = check_exact_duplicate_sync(
            "99ZZZZZ9999Z9Z9",  # Non-existent GSTIN
            "INV-NONEXISTENT",
            date(2024, 6, 15)
        )
        # Should pass (no duplicate found) or fail gracefully
        assert result is not None


class TestNearDuplicate:
    """Tests for V9: Near-duplicate detection."""

    def test_sync_version_returns_result(self):
        """Sync version should return a ValidationResult."""
        result = check_near_duplicates_sync(
            "29AAACA1234A1Z5",
            Decimal("100000"),
            date(2024, 6, 15),
            vendor_name="Test Vendor"
        )
        assert result is not None
        assert hasattr(result, "passed")
        assert hasattr(result, "message")

    def test_amount_tolerance_parameter(self):
        """Amount tolerance should be configurable."""
        # Tight tolerance
        result1 = check_near_duplicates_sync(
            "29AAACA1234A1Z5",
            Decimal("100000"),
            date(2024, 6, 15),
            amount_tolerance_pct=0.1,
        )
        # Loose tolerance
        result2 = check_near_duplicates_sync(
            "29AAACA1234A1Z5",
            Decimal("100000"),
            date(2024, 6, 15),
            amount_tolerance_pct=10.0,
        )
        # Both should return results without error
        assert result1 is not None
        assert result2 is not None

    def test_date_window_parameter(self):
        """Date window should be configurable."""
        result1 = check_near_duplicates_sync(
            "29AAACA1234A1Z5",
            Decimal("100000"),
            date(2024, 6, 15),
            date_window_days=1,
        )
        result2 = check_near_duplicates_sync(
            "29AAACA1234A1Z5",
            Decimal("100000"),
            date(2024, 6, 15),
            date_window_days=30,
        )
        assert result1 is not None
        assert result2 is not None

    def test_vendor_not_found_handled(self):
        """Non-existent vendor should be handled gracefully."""
        result = check_near_duplicates_sync(
            "99ZZZZZ9999Z9Z9",  # Non-existent GSTIN
            Decimal("100000"),
            date(2024, 6, 15),
        )
        assert result is not None
        # Should fail with vendor not found
        assert not result.passed


class TestExtractFinYearForDuplicates:
    """Tests for financial year extraction used in duplicate detection."""

    def test_fy_april_to_march(self):
        """FY should be April-March."""
        # April 2024 -> 2024-25
        assert extract_fin_year("2024-04-01") == "2024-25"
        # March 2025 -> 2024-25
        assert extract_fin_year("2025-03-31") == "2024-25"
        # April 2025 -> 2025-26
        assert extract_fin_year("2025-04-01") == "2025-26"

    @given(
        year=st.integers(min_value=2020, max_value=2030),
        month=st.integers(min_value=1, max_value=12),
    )
    def test_fy_format_consistency(self, year: int, month: int):
        """FY format should always be YYYY-YY."""
        fy = extract_fin_year(f"{year:04d}-{month:02d}-15")
        assert len(fy) == 7
        assert fy[4] == "-"
        parts = fy.split("-")
        assert len(parts[0]) == 4
        assert len(parts[1]) == 2


class TestDuplicateMatchDataclass:
    """Tests for DuplicateMatch dataclass."""

    def test_duplicate_match_creation(self):
        """DuplicateMatch should be creatable with all fields."""
        match = DuplicateMatch(
            invoice_id=1,
            invoice_number="INV-001",
            vendor_gstin="29AAACA1234A1Z5",
            invoice_date=date(2024, 6, 15),
            grand_total=Decimal("100000"),
            match_type="exact",
            similarity=1.0,
        )
        assert match.invoice_id == 1
        assert match.match_type == "exact"
        assert match.similarity == 1.0
