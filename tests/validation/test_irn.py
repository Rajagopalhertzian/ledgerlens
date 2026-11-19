"""Property-based tests for IRN validation (V6)."""

from hypothesis import given, strategies as st, settings
import hashlib

from ledgerlens.validation.irn import (
    compute_irn,
    validate_irn,
    extract_fin_year,
    validate_irn_from_invoice,
)


class TestComputeIRN:
    """Tests for IRN computation."""

    def test_compute_irn_deterministic(self):
        """Same inputs always produce same IRN."""
        irn1 = compute_irn("29AAACA1234A1Z5", "INV", "INV-001", "2024-25")
        irn2 = compute_irn("29AAACA1234A1Z5", "INV", "INV-001", "2024-25")
        assert irn1 == irn2

    def test_compute_irn_returns_64_hex_chars(self):
        """IRN should be 64 hex characters."""
        irn = compute_irn("29AAACA1234A1Z5", "INV", "INV-001", "2024-25")
        assert len(irn) == 64
        # Should be valid hex
        int(irn, 16)

    def test_compute_irn_case_insensitive_inputs(self):
        """Inputs should be normalized (uppercase, trimmed)."""
        irn1 = compute_irn("29AAACA1234A1Z5", "INV", "INV-001", "2024-25")
        irn2 = compute_irn(" 29aaaca1234a1z5 ", " inv ", " inv-001 ", " 2024-25 ")
        assert irn1 == irn2

    @given(
        supplier_gstin=st.text(alphabet="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=15, max_size=15),
        doc_type=st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=1, max_size=10),
        doc_number=st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-", min_size=1, max_size=20),
        fin_year=st.text(alphabet="0123456789-", min_size=7, max_size=7),
    )
    @settings(max_examples=50)
    def test_compute_irn_always_returns_64_hex(
        self, supplier_gstin: str, doc_type: str, doc_number: str, fin_year: str
    ):
        """IRN computation always returns 64 hex chars for any valid input."""
        irn = compute_irn(supplier_gstin, doc_type, doc_number, fin_year)
        assert len(irn) == 64
        int(irn, 16)  # Should not raise

    def test_different_inputs_produce_different_irns(self):
        """Different inputs should produce different IRNs (with high probability)."""
        irn1 = compute_irn("29AAACA1234A1Z5", "INV", "INV-001", "2024-25")
        irn2 = compute_irn("29AAACA1234A1Z5", "INV", "INV-002", "2024-25")
        irn3 = compute_irn("27BBBCB5678B2Z6", "INV", "INV-001", "2024-25")
        irn4 = compute_irn("29AAACA1234A1Z5", "INV", "INV-001", "2023-24")

        assert irn1 != irn2
        assert irn1 != irn3
        assert irn1 != irn4


class TestValidateIRN:
    """Tests for IRN validation."""

    def test_valid_irn_passes(self):
        """Correct IRN should pass validation."""
        supplier_gstin = "29AAACA1234A1Z5"
        doc_type = "INV"
        doc_number = "INV-001"
        fin_year = "2024-25"
        expected_irn = compute_irn(supplier_gstin, doc_type, doc_number, fin_year)

        result = validate_irn(expected_irn, supplier_gstin, doc_type, doc_number, fin_year)
        assert result.passed
        assert result.details is not None
        assert result.details["computed_irn"] == expected_irn

    def test_invalid_irn_fails(self):
        """Incorrect IRN should fail validation."""
        supplier_gstin = "29AAACA1234A1Z5"
        doc_type = "INV"
        doc_number = "INV-001"
        fin_year = "2024-25"
        wrong_irn = "0" * 64  # All zeros

        result = validate_irn(wrong_irn, supplier_gstin, doc_type, doc_number, fin_year)
        assert not result.passed
        assert "MISMATCH" in result.message

    def test_empty_irn_fails(self):
        """Empty IRN should fail."""
        result = validate_irn("", "29AAACA1234A1Z5", "INV", "INV-001", "2024-25")
        assert not result.passed

    def test_wrong_length_irn_fails(self):
        """IRN with wrong length should fail."""
        result = validate_irn("abc", "29AAACA1234A1Z5", "INV", "INV-001", "2024-25")
        assert not result.passed
        assert "64 hex characters" in result.message

    def test_non_hex_irn_fails(self):
        """Non-hex IRN should fail."""
        result = validate_irn("G" * 64, "29AAACA1234A1Z5", "INV", "INV-001", "2024-25")
        assert not result.passed
        assert "not valid hex" in result.message

    @given(
        supplier_gstin=st.text(alphabet="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=15, max_size=15),
        doc_type=st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=1, max_size=10),
        doc_number=st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-", min_size=1, max_size=20),
        fin_year=st.text(alphabet="0123456789-", min_size=7, max_size=7),
    )
    @settings(max_examples=50)
    def test_validate_irn_with_computed_irn_passes(
        self, supplier_gstin: str, doc_type: str, doc_number: str, fin_year: str
    ):
        """Validating a correctly computed IRN should always pass."""
        irn = compute_irn(supplier_gstin, doc_type, doc_number, fin_year)
        result = validate_irn(irn, supplier_gstin, doc_type, doc_number, fin_year)
        assert result.passed


class TestExtractFinYear:
    """Tests for financial year extraction."""

    def test_april_onwards_is_next_fy(self):
        """April onwards should be in next financial year."""
        # April 2024 -> FY 2024-25
        assert extract_fin_year("2024-04-01") == "2024-25"
        assert extract_fin_year("2024-04-15") == "2024-25"
        assert extract_fin_year("2024-12-31") == "2024-25"
        assert extract_fin_year("2025-03-31") == "2024-25"

    def test_jan_march_is_previous_fy(self):
        """Jan-March should be in previous financial year."""
        # January 2025 -> FY 2024-25
        assert extract_fin_year("2025-01-01") == "2024-25"
        assert extract_fin_year("2025-03-15") == "2024-25"

    def test_fy_format(self):
        """FY format should be YYYY-YY."""
        fy = extract_fin_year("2024-06-15")
        assert len(fy) == 7
        assert fy[4] == "-"
        # First part is 4 digits, second is 2 digits
        parts = fy.split("-")
        assert len(parts[0]) == 4
        assert len(parts[1]) == 2

    @given(
        year=st.integers(min_value=2000, max_value=2099),
        month=st.integers(min_value=1, max_value=12),
        day=st.integers(min_value=1, max_value=28),
    )
    @settings(max_examples=100)
    def test_extract_fin_year_always_returns_valid_format(self, year: int, month: int, day: int):
        """extract_fin_year should always return valid YYYY-YY format."""
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        fy = extract_fin_year(date_str)
        assert len(fy) == 7
        assert fy[4] == "-"
        parts = fy.split("-")
        assert parts[0].isdigit() and len(parts[0]) == 4
        assert parts[1].isdigit() and len(parts[1]) == 2


class TestValidateIRNFromInvoice:
    """Tests for validating IRN from invoice data."""

    def test_valid_irn_from_invoice_passes(self):
        """Valid IRN with invoice data should pass."""
        supplier_gstin = "29AAACA1234A1Z5"
        invoice_number = "INV-001"
        invoice_date = "2024-06-15"  # FY 2024-25
        doc_type = "INV"

        irn = compute_irn(supplier_gstin, doc_type, invoice_number, "2024-25")
        result = validate_irn_from_invoice(irn, supplier_gstin, invoice_number, invoice_date, doc_type)
        assert result.passed

    def test_wrong_irn_from_invoice_fails(self):
        """Wrong IRN with invoice data should fail."""
        result = validate_irn_from_invoice(
            "0" * 64, "29AAACA1234A1Z5", "INV-001", "2024-06-15", "INV"
        )
        assert not result.passed


# Test that IRN computation matches e-invoice spec
# Spec: IRN = SHA-256(supplier_gstin + doc_type + doc_number + fin_year)
class TestIRNSpecCompliance:
    """Test IRN computation matches official e-invoice specification."""

    def test_irn_matches_sha256_of_concatenated_fields(self):
        """IRN should be SHA-256 of concatenated fields per spec."""
        supplier_gstin = "29AAACA1234A1Z5"
        doc_type = "INV"
        doc_number = "INV-001"
        fin_year = "2024-25"

        payload = f"{supplier_gstin}{doc_type}{doc_number}{fin_year}"
        expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        irn = compute_irn(supplier_gstin, doc_type, doc_number, fin_year)
        assert irn == expected

    def test_irn_verification_matches_spec(self):
        """Validation should use same computation as spec."""
        supplier_gstin = "29AAACA1234A1Z5"
        doc_type = "INV"
        doc_number = "INV-001"
        fin_year = "2024-25"

        payload = f"{supplier_gstin}{doc_type}{doc_number}{fin_year}"
        expected_irn = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        result = validate_irn(expected_irn, supplier_gstin, doc_type, doc_number, fin_year)
        assert result.passed
        assert result.details is not None
        assert result.details["computed_irn"] == expected_irn
