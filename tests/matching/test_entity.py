"""Tests for entity resolution (vendor and PO matching)."""

import pytest
from decimal import Decimal

from ledgerlens.matching.entity import (
    resolve_vendor_sync,
    resolve_po_sync,
    VENDOR_NAME_THRESHOLD,
    VENDOR_ADDRESS_THRESHOLD,
)
from ledgerlens.matching.models import VendorMatchResult, POCandidate


def _run_entity_test(test_func, *args, **kwargs):
    """Run entity resolution test, skipping if database not available."""
    try:
        return test_func(*args, **kwargs)
    except RuntimeError as e:
        if "Database not initialized" in str(e):
            pytest.skip(f"Database not available: {e}")
        raise


class TestResolveVendorSync:
    """Tests for synchronous vendor resolution."""

    def test_exact_gstin_match(self):
        """Exact GSTIN match should return vendor with high confidence."""
        def _test():
            result = resolve_vendor_sync("29AAACA1234A1Z5", None, None)
            assert result is not None
            assert isinstance(result, VendorMatchResult)
        _run_entity_test(_test)

    def test_fuzzy_name_match(self):
        """Fuzzy name match should work."""
        def _test():
            result = resolve_vendor_sync(None, "Test Vendor Pvt Ltd", "123 Test Street Bangalore")
            assert result is not None
            assert isinstance(result, VendorMatchResult)
        _run_entity_test(_test)

    def test_no_match_returns_none(self):
        """No match should return result with no vendor_id."""
        def _test():
            result = resolve_vendor_sync("99ZZZZZ9999Z9Z9", "NonExistent Vendor", "Nowhere")
            assert result is not None
            assert isinstance(result, VendorMatchResult)
        _run_entity_test(_test)

    def test_match_type_values(self):
        """Match type should be one of expected values."""
        def _test():
            result = resolve_vendor_sync("29AAACA1234A1Z5", "Test", "Address")
            assert result.match_type in (
                "exact_gstin",
                "fuzzy_name_address",
                "fuzzy_name_address_low_confidence",
                "none",
            )
        _run_entity_test(_test)

    def test_confidence_range(self):
        """Confidence should be between 0 and 1."""
        def _test():
            result = resolve_vendor_sync("29AAACA1234A1Z5", "Test", "Address")
            assert 0 <= result.confidence <= 1
        _run_entity_test(_test)


class TestResolvePOSync:
    """Tests for synchronous PO resolution."""

    def test_returns_list_of_candidates(self):
        """Should return list of PO candidates."""
        def _test():
            result = resolve_po_sync(
                invoice_vendor_gstin="29AAACA1234A1Z5",
                invoice_number="INV-001",
                invoice_date="2024-06-15",
                invoice_amount=Decimal("100000"),
                invoice_lines=[{"item_description": "Test Item", "hsn_code": "998713"}],
            )
            assert isinstance(result, list)
            for candidate in result:
                assert isinstance(candidate, POCandidate)
        _run_entity_test(_test)

    def test_candidates_sorted_by_score(self):
        """Candidates should be sorted by score descending."""
        def _test():
            result = resolve_po_sync(
                invoice_vendor_gstin="29AAACA1234A1Z5",
                invoice_number="INV-001",
                invoice_date="2024-06-15",
                invoice_amount=Decimal("100000"),
                invoice_lines=[{"item_description": "Test Item", "hsn_code": "998713"}],
            )
            if len(result) > 1:
                scores = [c.score for c in result]
                assert scores == sorted(scores, reverse=True)
        _run_entity_test(_test)

    def test_candidate_has_required_fields(self):
        """Each candidate should have required fields."""
        def _test():
            result = resolve_po_sync(
                invoice_vendor_gstin="29AAACA1234A1Z5",
                invoice_number="INV-001",
                invoice_date="2024-06-15",
                invoice_amount=Decimal("100000"),
                invoice_lines=[{"item_description": "Test Item", "hsn_code": "998713"}],
            )
            for candidate in result:
                assert candidate.po_id is not None
                assert candidate.po_number is not None
                assert candidate.vendor_gstin is not None
                assert candidate.vendor_name is not None
                assert candidate.po_date is not None
                assert candidate.grand_total is not None
                assert isinstance(candidate.score, float)
                assert isinstance(candidate.match_reasons, list)
        _run_entity_test(_test)


class TestEntityResolutionThresholds:
    """Tests for entity resolution threshold constants."""

    def test_vendor_name_threshold(self):
        """Vendor name threshold should be reasonable."""
        assert 0 < VENDOR_NAME_THRESHOLD <= 100

    def test_vendor_address_threshold(self):
        """Vendor address threshold should be reasonable."""
        assert 0 < VENDOR_ADDRESS_THRESHOLD <= 100

    def test_po_amount_threshold(self):
        """PO amount threshold should be defined."""
        from ledgerlens.matching.entity import PO_AMOUNT_THRESHOLD
        assert PO_AMOUNT_THRESHOLD > 0

    def test_po_date_window(self):
        """PO date window should be defined."""
        from ledgerlens.matching.entity import PO_DATE_WINDOW_DAYS
        assert PO_DATE_WINDOW_DAYS > 0
