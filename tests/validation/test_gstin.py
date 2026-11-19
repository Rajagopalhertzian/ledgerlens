"""Property-based tests for GSTIN validation (V1, V2)."""

import pytest
from hypothesis import given, strategies as st, settings

from ledgerlens.validation.gstin import (
    validate_gstin_format,
    validate_gstin_checksum,
    validate_state_code,
    validate_gstin_full,
    CHECKSUM_CHARS,
    WEIGHTS,
    VALID_STATE_CODES,
)


class TestGSTINChecksum:
    """Property-based tests for GSTIN checksum algorithm."""

    @given(st.text(alphabet=CHECKSUM_CHARS, min_size=14, max_size=14))
    @settings(max_examples=100)
    def test_checksum_calculation_is_deterministic(self, base_gstin: str):
        """Same input always produces same checksum."""
        result1 = validate_gstin_checksum(base_gstin + "0")
        result2 = validate_gstin_checksum(base_gstin + "0")
        assert result1.passed == result2.passed
        assert result1.details is not None
        assert result2.details is not None
        assert result1.details["expected_checksum"] == result2.details["expected_checksum"]

    @given(st.text(alphabet=CHECKSUM_CHARS, min_size=15, max_size=15))
    @settings(max_examples=100)
    def test_valid_checksum_always_passes(self, gstin: str):
        """A GSTIN with correct checksum should pass validation."""
        # Calculate correct checksum for first 14 chars
        base = gstin[:14]
        total = 0
        for i, ch in enumerate(base):
            val = CHECKSUM_CHARS.index(ch)
            total += val * WEIGHTS[i]
        check_val = (36 - (total % 36)) % 36
        correct_checksum = CHECKSUM_CHARS[check_val]
        correct_gstin = base + correct_checksum

        result = validate_gstin_checksum(correct_gstin)
        assert result.passed, f"Valid checksum failed: {result.details}"

    @given(st.text(alphabet=CHECKSUM_CHARS, min_size=14, max_size=14))
    @settings(max_examples=100)
    def test_wrong_checksum_fails(self, base: str):
        """Any wrong checksum should fail."""
        total = 0
        for i, ch in enumerate(base):
            val = CHECKSUM_CHARS.index(ch)
            total += val * WEIGHTS[i]
        check_val = (36 - (total % 36)) % 36
        correct_checksum = CHECKSUM_CHARS[check_val]

        # Try all wrong checksums
        for wrong_checksum in CHECKSUM_CHARS:
            if wrong_checksum != correct_checksum:
                gstin = base + wrong_checksum
                result = validate_gstin_checksum(gstin)
                assert not result.passed, f"Wrong checksum {wrong_checksum} incorrectly passed"


class TestGSTINFormat:
    """Tests for GSTIN format validation."""

    @given(st.text(min_size=15, max_size=15))
    @settings(max_examples=50)
    def test_format_validates_length(self, gstin: str):
        """GSTIN must be exactly 15 characters."""
        result = validate_gstin_format(gstin)
        # If length is 15 but format invalid, it should still fail
        # If length is not 15, it should fail
        if len(gstin) != 15:
            assert not result.passed
        else:
            # For 15 chars, passed depends on format matching pattern
            pass  # Just verify no crash

    def test_known_valid_gstins_pass(self):
        """Known valid GSTINs should pass format validation."""
        valid_gstins = [
            "29AAACA1234A1Z3",
            "27BBBCB5678B2ZR",
            "07AAACC8901C3ZX",
        ]
        for gstin in valid_gstins:
            result = validate_gstin_format(gstin)
            assert result.passed, f"Known valid GSTIN {gstin} failed: {result.message}"

    def test_invalid_length_fails(self):
        """GSTINs with wrong length should fail."""
        for gstin in ["29AAACA1234A1Z", "29AAACA1234A1Z55", ""]:
            result = validate_gstin_format(gstin)
            assert not result.passed


class TestStateCodeValidation:
    """Tests for state code validation."""

    @given(st.sampled_from(list(VALID_STATE_CODES)))
    def test_valid_state_codes_pass(self, state_code: str):
        """All valid state codes should pass."""
        gstin = state_code + "AAACA1234A1Z5"
        result = validate_state_code(gstin)
        assert result.passed, f"Valid state code {state_code} failed"

    @given(st.text(alphabet="0123456789", min_size=2, max_size=2).filter(lambda x: x not in VALID_STATE_CODES))
    @settings(max_examples=50)
    def test_invalid_state_codes_fail(self, state_code: str):
        """Invalid state codes should fail."""
        gstin = state_code + "AAACA1234A1Z5"
        result = validate_state_code(gstin)
        assert not result.passed


class TestGSTINFullValidation:
    """Tests for complete GSTIN validation."""

    def test_full_validation_runs_all_checks(self):
        """Full validation should run format, checksum, and state code checks."""
        gstin = "29AAACA1234A1Z3"  # Valid checksum
        results = validate_gstin_full(gstin)
        assert len(results) == 3
        assert all(r.passed for r in results)

    def test_invalid_gstin_fails_at_least_one(self):
        """Invalid GSTIN should fail at least one validation."""
        gstin = "XXAAACA1234A1Z5"  # Invalid state code
        results = validate_gstin_full(gstin)
        assert any(not r.passed for r in results)


class TestGSTINVendorMatch:
    """Tests for V2: GSTIN vendor master match (sync version)."""

    def test_sync_version_runs_without_session(self):
        """Sync version should not require explicit session."""
        from ledgerlens.validation.gstin import validate_gstin_vendor_match_sync

        # This will create its own session and fail gracefully if no DB
        result = validate_gstin_vendor_match_sync("29AAACA1234A1Z5")
        # Should not crash - returns ValidationResult
        assert result is not None
        assert hasattr(result, "passed")
        assert hasattr(result, "message")


# Known valid GSTINs for testing (format: state + PAN + entity + Z + checksum)
# These have correct checksums calculated per GSTIN spec
KNOWN_VALID_GSTINS = [
    "29AAACA1234A1Z3",  # Karnataka
    "27BBBCB5678B2ZR",  # Maharashtra
    "07AAACC8901C3ZX",  # Delhi
    "33AAADD2345D4ZI",  # Tamil Nadu
]


class TestKnownValidGSTINs:
    """Test with known valid GSTINs."""

    @pytest.mark.parametrize("gstin", KNOWN_VALID_GSTINS)
    def test_known_valid_gstin_passes_all(self, gstin: str):
        """Known valid GSTINs should pass all validations."""
        results = validate_gstin_full(gstin)
        assert all(r.passed for r in results), f"GSTIN {gstin} failed: {[r.message for r in results if not r.passed]}"
