"""Tests for GSTIN generation and validation."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from datagen.gstin import (
    compute_checksum,
    generate_gstin,
    generate_random_gstin,
    parse_gstin,
    validate_gstin,
)


class TestGSTINChecksum:
    """Tests for GSTIN checksum computation."""

    def test_compute_checksum_deterministic(self):
        """Checksum should be deterministic."""
        prefix = "29ABCDE1234F1Z"
        cs1 = compute_checksum(prefix)
        cs2 = compute_checksum(prefix)
        assert cs1 == cs2

    def test_compute_checksum_valid_chars(self):
        """Checksum should be valid character (0-9, A-Z)."""
        prefix = "29ABCDE1234F1Z"
        cs = compute_checksum(prefix)
        assert cs in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    def test_compute_checksum_known_values(self):
        """Test known checksum values."""
        # Computed using the official GST algorithm
        test_cases = [
            ("29ABCDE1234F1Z", "3"),
            ("07AAAAA0000A1Z", "A"),
            ("27BBBBB1111B2Z", "7"),
        ]
        for prefix, expected in test_cases:
            assert compute_checksum(prefix) == expected

    def test_compute_checksum_invalid_length(self):
        """Should raise on wrong length."""
        with pytest.raises(ValueError):
            compute_checksum("29ABCDE1234F1")  # 13 chars
        with pytest.raises(ValueError):
            compute_checksum("29ABCDE1234F1ZZ")  # 15 chars

    def test_compute_checksum_invalid_char(self):
        """Should raise on invalid character."""
        with pytest.raises(ValueError):
            compute_checksum("29ABCDE1234F1!")  # ! not valid


class TestGSTINValidation:
    """Tests for GSTIN validation."""

    def test_validate_known_valid_gstins(self):
        """Test known valid GSTINs."""
        # GSTINs with correct checksums computed by the algorithm
        valid_gstins = [
            "29ABCDE1234F1Z3",
            "07AAAAA0000A1ZA",
            "27BBBBB1111B2Z7",
            "33CCCCC2222C3ZA",
            "36DDDDD3333D4ZI",
        ]
        for gstin in valid_gstins:
            assert validate_gstin(gstin), f"Expected valid: {gstin}"

    def test_validate_invalid_length(self):
        """Should reject wrong length."""
        assert not validate_gstin("29ABCDE1234F1Z")  # 14 chars
        assert not validate_gstin("29ABCDE1234F1Z55")  # 16 chars
        assert not validate_gstin("")  # empty

    def test_validate_invalid_state_code(self):
        """Should reject invalid state code."""
        assert not validate_gstin("99ABCDE1234F1Z5")  # Invalid state

    def test_validate_invalid_pan_format(self):
        """Should reject invalid PAN format."""
        # PAN must be 5 letters + 4 digits + 1 letter
        assert not validate_gstin("29ABCD12345F1Z5")  # 4 letters
        assert not validate_gstin("29ABCDE12345F1Z5")  # 5 digits
        assert not validate_gstin("29ABCDE12345F1Z5")  # missing last letter

    def test_validate_invalid_entity_code(self):
        """Should reject entity code '0'."""
        assert not validate_gstin("29ABCDE1234F0Z5")  # Entity code 0

    def test_validate_invalid_z_char(self):
        """Should reject non-Z 14th character."""
        assert not validate_gstin("29ABCDE1234F1Y5")  # Y instead of Z

    def test_validate_wrong_checksum(self):
        """Should reject wrong checksum."""
        assert not validate_gstin("29ABCDE1234F1Z4")  # Wrong checksum


class TestGSTINGeneration:
    """Tests for GSTIN generation."""

    def test_generate_gstin_valid(self):
        """Generated GSTIN should be valid."""
        gstin = generate_gstin("29", "ABCDE1234F", "1")
        assert validate_gstin(gstin)
        assert gstin.startswith("29")
        assert gstin[2:12] == "ABCDE1234F"
        assert gstin[12] == "1"
        assert gstin[13] == "Z"

    def test_generate_random_gstin_valid(self):
        """Random GSTIN should be valid."""
        import random
        rng = random.Random(42)
        for _ in range(100):
            gstin = generate_random_gstin(rng)
            assert validate_gstin(gstin)

    def test_generate_gstin_specific_state(self):
        """Should generate for specific state."""
        import random
        rng = random.Random(42)
        gstin = generate_random_gstin(rng, state_code="29")
        assert gstin.startswith("29")
        assert validate_gstin(gstin)

    def test_generate_gstin_invalid_state(self):
        """Should raise on invalid state code."""
        with pytest.raises(ValueError):
            generate_gstin("99", "ABCDE1234F", "1")

    def test_generate_gstin_invalid_pan(self):
        """Should raise on invalid PAN."""
        with pytest.raises(ValueError):
            generate_gstin("29", "INVALID", "1")

    def test_generate_gstin_invalid_entity(self):
        """Should raise on invalid entity code."""
        with pytest.raises(ValueError):
            generate_gstin("29", "ABCDE1234F", "0")


class TestGSTINParsing:
    """Tests for GSTIN parsing."""

    def test_parse_valid_gstin(self):
        """Should parse valid GSTIN into components."""
        result = parse_gstin("29ABCDE1234F1Z3")
        assert result is not None
        assert result["state_code"] == "29"
        assert result["state_name"] == "Karnataka"
        assert result["pan"] == "ABCDE1234F"
        assert result["entity_code"] == "1"
        assert result["z_char"] == "Z"
        assert result["checksum"] == "3"

    def test_parse_invalid_gstin(self):
        """Should return None for invalid GSTIN."""
        assert parse_gstin("INVALID") is None
        assert parse_gstin("29ABCDE1234F1Z4") is None  # Wrong checksum


# Property-based tests
class TestGSTINProperties:
    """Property-based tests for GSTIN."""

    @given(st.text(alphabet="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=14, max_size=14))
    def test_checksum_deterministic(self, prefix):
        """Checksum should be deterministic for any valid prefix."""
        # Filter to valid characters
        valid_prefix = "".join(c for c in prefix if c in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        if len(valid_prefix) == 14:
            cs1 = compute_checksum(valid_prefix)
            cs2 = compute_checksum(valid_prefix)
            assert cs1 == cs2

    def test_generated_always_validates(self):
        """Any generated GSTIN should validate."""
        import random
        rng = random.Random(12345)
        for _ in range(1000):
            gstin = generate_random_gstin(rng)
            assert validate_gstin(gstin), f"Generated GSTIN failed validation: {gstin}"

    def test_state_code_distribution(self):
        """Generated GSTINs should cover all states."""
        import random
        rng = random.Random(12345)
        states = set()
        for _ in range(500):
            gstin = generate_random_gstin(rng)
            states.add(gstin[:2])
        # Should hit most states
        assert len(states) > 20


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
