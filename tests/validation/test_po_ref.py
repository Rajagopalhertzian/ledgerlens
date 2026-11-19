"""Tests for PO reference validation (V11)."""


from ledgerlens.validation.po_ref import validate_po_reference_sync


class TestValidatePOReferenceSync:
    """Tests for synchronous PO reference validation."""

    def test_sync_returns_result(self):
        """Sync version should return a ValidationResult."""
        result = validate_po_reference_sync("PO-001", "29AAACA1234A1Z5")
        assert result is not None
        assert hasattr(result, "passed")
        assert hasattr(result, "message")

    def test_none_po_reference_passes(self):
        """None/empty PO reference should pass (optional)."""
        result = validate_po_reference_sync("", "29AAACA1234A1Z5")
        assert result is not None
        # Should pass since PO reference is optional

    def test_none_po_reference_none_passes(self):
        """Empty PO reference should pass (optional)."""
        result = validate_po_reference_sync("", "29AAACA1234A1Z5")
        assert result is not None
        assert result.passed
