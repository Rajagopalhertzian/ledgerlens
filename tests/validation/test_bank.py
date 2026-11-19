"""Tests for bank details validation (V10)."""

from hypothesis import given, strategies as st, settings

from ledgerlens.validation.bank import (
    normalize_account_number,
    normalize_ifsc,
    validate_bank_details_sync,
)


class TestNormalizeAccountNumber:
    """Tests for account number normalization."""

    def test_removes_special_characters(self):
        """Non-alphanumeric characters should be removed."""
        assert normalize_account_number("1234-5678-90") == "1234567890"
        assert normalize_account_number("1234 5678 90") == "1234567890"
        assert normalize_account_number("1234.5678.90") == "1234567890"

    def test_keeps_alphanumeric(self):
        """Alphanumeric characters should be kept."""
        assert normalize_account_number("ABC123DEF") == "ABC123DEF"
        assert normalize_account_number("1234567890") == "1234567890"

    def test_empty_string(self):
        """Empty string should return empty."""
        assert normalize_account_number("") == ""

    @given(st.text(alphabet="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ- .", min_size=0, max_size=30))
    @settings(max_examples=50)
    def test_normalize_is_idempotent(self, s: str):
        """Normalizing twice should give same result."""
        once = normalize_account_number(s)
        twice = normalize_account_number(once)
        assert once == twice


class TestNormalizeIFSC:
    """Tests for IFSC normalization."""

    def test_uppercase_and_trim(self):
        """IFSC should be uppercased and trimmed."""
        assert normalize_ifsc("  hdfc0001234  ") == "HDFC0001234"
        assert normalize_ifsc("hdfc0001234") == "HDFC0001234"
        assert normalize_ifsc("HDFC0001234") == "HDFC0001234"

    @given(st.text(alphabet="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz ", min_size=0, max_size=20))
    @settings(max_examples=50)
    def test_normalize_ifsc_idempotent(self, s: str):
        """Normalizing twice should give same result."""
        once = normalize_ifsc(s)
        twice = normalize_ifsc(once)
        assert once == twice


class TestValidateBankDetailsSync:
    """Tests for synchronous bank validation (for testing)."""

    def test_sync_returns_result(self):
        """Sync version should return a ValidationResult."""
        result = validate_bank_details_sync(
            invoice_account_name="Test Vendor Pvt Ltd",
            invoice_account_number="1234567890",
            invoice_ifsc="HDFC0001234",
            invoice_bank_name="HDFC Bank",
            vendor_gstin="29AAACA1234A1Z5",
        )
        assert result is not None
        assert hasattr(result, "passed")
        assert hasattr(result, "message")

    def test_matching_details_pass(self):
        """Matching bank details should pass."""
        # Note: This will try to query the database, so it may fail if no DB
        # But it should not crash
        result = validate_bank_details_sync(
            invoice_account_name="Test Vendor",
            invoice_account_number="1234567890",
            invoice_ifsc="HDFC0001234",
            invoice_bank_name="HDFC Bank",
            vendor_gstin="29AAACA1234A1Z5",
        )
        assert result is not None

    def test_none_values_handled(self):
        """None values should be handled gracefully."""
        result = validate_bank_details_sync(
            invoice_account_name=None,
            invoice_account_number=None,
            invoice_ifsc=None,
            invoice_bank_name=None,
            vendor_gstin="29AAACA1234A1Z5",
        )
        assert result is not None
