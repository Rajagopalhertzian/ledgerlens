"""Tests for 3-way matching (Invoice-PO-GRN)."""

import pytest
from decimal import Decimal
from datetime import date

from ledgerlens.matching.three_way import (
    match_invoice_po_grn,
    normalize_uom,
    compute_line_similarity,
    build_cost_matrix,
    _evaluate_line_match,
    _calculate_summary,
    _determine_overall_status,
)
from ledgerlens.matching.models import (
    MatchResult, MatchStatus, LineMatchResult, LineMatchStatus,
    MatchingConfig
)
from ledgerlens.db.models import Invoice, InvoiceLine, PurchaseOrder, POLine, GoodsReceipt, GRNLine, TaxType


def _run_matching_test(test_func, *args, **kwargs):
    """Run matching test, skipping if database not available."""
    try:
        return test_func(*args, **kwargs)
    except RuntimeError as e:
        if "Database not initialized" in str(e):
            pytest.skip(f"Database not available: {e}")
        raise


class TestNormalizeUOM:
    """Tests for UoM normalization."""

    def test_same_uom_returns_same_qty(self):
        """Same UoM should return unchanged quantity."""
        qty = Decimal("100")
        result = normalize_uom(qty, "PCS", "PCS", MatchingConfig())
        assert result == qty

    def test_kg_to_g_conversion(self):
        """KG to G conversion should work."""
        config = MatchingConfig()
        config.uom_conversions = {"KG": {"G": Decimal("1000")}}
        qty = Decimal("1")
        result = normalize_uom(qty, "KG", "G", config)
        assert result == Decimal("1000")

    def test_g_to_kg_conversion(self):
        """G to KG conversion should work."""
        config = MatchingConfig()
        config.uom_conversions = {"KG": {"G": Decimal("1000")}}
        qty = Decimal("1000")
        result = normalize_uom(qty, "G", "KG", config)
        assert result == Decimal("1")

    def test_no_conversion_returns_original(self):
        """No conversion available should return original."""
        config = MatchingConfig()
        config.uom_conversions = {}
        qty = Decimal("100")
        result = normalize_uom(qty, "PCS", "BOX", config)
        assert result == qty


class TestComputeLineSimilarity:
    """Tests for line similarity computation."""

    def test_exact_match_high_score(self):
        """Identical lines should have high similarity."""
        inv_line = InvoiceLine(
            invoice_id=1, line_number=1, item_code="ITEM1", item_description="Test Item",
            hsn_code="998713", uom="PCS", quantity=Decimal("100"), unit_price=Decimal("1000"),
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST,
            taxable_value=Decimal("100000"), tax_amount=Decimal("18000"), line_total=Decimal("118000"),
        )
        po_line = POLine(
            po_id=1, line_number=1, item_code="ITEM1", item_description="Test Item",
            hsn_code="998713", uom="PCS", quantity=Decimal("100"), unit_price=Decimal("1000"),
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST,
            taxable_value=Decimal("100000"), tax_amount=Decimal("18000"), line_total=Decimal("118000"),
        )
        grn_line = GRNLine(
            grn_id=1, line_number=1, po_line_id=1,
            quantity_received=Decimal("100"), quantity_accepted=Decimal("100"), quantity_rejected=Decimal("0"),
        )
        # Need to set po_line on grn_line for UoM access
        grn_line.po_line = po_line

        config = MatchingConfig()
        score = compute_line_similarity(inv_line, po_line, grn_line, config)
        assert score > 90  # Should be very high

    def test_hsn_match_adds_score(self):
        """HSN match should add significant score."""
        inv_line = InvoiceLine(
            invoice_id=1, line_number=1, item_code="ITEM1", item_description="Test Item",
            hsn_code="998713", uom="PCS", quantity=Decimal("100"), unit_price=Decimal("1000"),
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST,
        )
        po_line = POLine(
            po_id=1, line_number=1, item_code="ITEM1", item_description="Different Desc",
            hsn_code="998713", uom="PCS", quantity=Decimal("100"), unit_price=Decimal("1000"),
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST,
        )
        config = MatchingConfig()
        score = compute_line_similarity(inv_line, po_line, None, config)
        # Should have at least 30 points for HSN match
        assert score >= 30

    def test_description_fuzzy_match(self):
        """Similar descriptions should add score."""
        inv_line = InvoiceLine(
            invoice_id=1, line_number=1, item_code="ITEM1", item_description="Laptop Computer",
            hsn_code="8471", uom="PCS", quantity=Decimal("1"), unit_price=Decimal("50000"),
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST,
        )
        po_line = POLine(
            po_id=1, line_number=1, item_code="ITEM1", item_description="Laptop Computer Pro",
            hsn_code="8471", uom="PCS", quantity=Decimal("1"), unit_price=Decimal("50000"),
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST,
        )
        config = MatchingConfig()
        score = compute_line_similarity(inv_line, po_line, None, config)
        # Should get some points for fuzzy description match
        assert score > 30

    def test_price_within_tolerance_adds_score(self):
        """Price within tolerance should add score."""
        inv_line = InvoiceLine(
            invoice_id=1, line_number=1, item_code="ITEM1", item_description="Test",
            hsn_code="998713", uom="PCS", quantity=Decimal("100"), unit_price=Decimal("1000"),
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST,
        )
        po_line = POLine(
            po_id=1, line_number=1, item_code="ITEM1", item_description="Test",
            hsn_code="998713", uom="PCS", quantity=Decimal("100"), unit_price=Decimal("1010"),  # 1% diff
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST,
        )
        config = MatchingConfig(price_tolerance_pct=2.0)
        score = compute_line_similarity(inv_line, po_line, None, config)
        # Should get price points
        assert score > 50


class TestBuildCostMatrix:
    """Tests for cost matrix building."""

    def test_square_matrix(self):
        """Cost matrix should be square."""
        inv_lines = [InvoiceLine(invoice_id=1, line_number=i, item_code=f"ITEM{i}", item_description="Test",
                                  hsn_code="998713", uom="PCS", quantity=Decimal("10"), unit_price=Decimal("100"),
                                  discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST)
                     for i in range(3)]
        po_lines = [POLine(po_id=1, line_number=i, item_code=f"ITEM{i}", item_description="Test",
                           hsn_code="998713", uom="PCS", quantity=Decimal("10"), unit_price=Decimal("100"),
                           discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST)
                    for i in range(2)]

        config = MatchingConfig()
        matrix = build_cost_matrix(inv_lines, po_lines, None, config)
        assert matrix.shape == (3, 3)  # max(3, 2) = 3

    def test_cost_is_inverse_similarity(self):
        """Cost should be 100 - similarity."""
        inv_lines = [InvoiceLine(invoice_id=1, line_number=1, item_code="ITEM1", item_description="Test",
                                  hsn_code="998713", uom="PCS", quantity=Decimal("10"), unit_price=Decimal("100"),
                                  discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST)]
        po_lines = [POLine(po_id=1, line_number=1, item_code="ITEM1", item_description="Test",
                           hsn_code="998713", uom="PCS", quantity=Decimal("10"), unit_price=Decimal("100"),
                           discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST)]

        config = MatchingConfig()
        matrix = build_cost_matrix(inv_lines, po_lines, None, config)
        # Perfect match should have cost near 0
        assert matrix[0, 0] < 10


class TestMatchInvoicePOGRN:
    """Tests for main matching function."""

    def test_sync_wrapper_calls_async(self):
        """Sync wrapper should call async version."""
        def _test():
            invoice = Invoice(
                id=1, invoice_number="INV-001", vendor_id=1,
                invoice_date=date(2024, 6, 15), due_date=date(2024, 7, 15),
                buyer_gstin="29BBBCB5678B2Z6", buyer_name="Test", buyer_address="Addr",
                buyer_state_code="29", place_of_supply="29", place_of_delivery="29",
                status="validated", currency="INR", subtotal=Decimal("1000"),
                total_tax=Decimal("180"), grand_total=Decimal("1180"),
            )
            po = PurchaseOrder(
                id=1, po_number="PO-001", vendor_id=1,
                po_date=date(2024, 1, 15), delivery_date=date(2024, 2, 15),
                buyer_gstin="29BBBCB5678B2Z6", buyer_name="Test", buyer_address="Addr",
                buyer_state_code="29", place_of_supply="29",
                status="open", currency="INR", subtotal=Decimal("1000"),
                total_tax=Decimal("180"), grand_total=Decimal("1180"),
            )
            grn = GoodsReceipt(
                id=1, grn_number="GRN-001", po_id=1, vendor_id=1,
                grn_date=date(2024, 2, 10), status="complete", received_by="Test",
            )

            config = MatchingConfig()
            result = match_invoice_po_grn(invoice, po, grn, config)
            assert isinstance(result, MatchResult)
            assert result.invoice_id == 1
            assert result.invoice_number == "INV-001"
        _run_matching_test(_test)

    def test_missing_po_returns_missing_po_status(self):
        """Missing PO should return MISSING_PO status."""
        def _test():
            invoice = Invoice(
                id=1, invoice_number="INV-001", vendor_id=1,
                invoice_date=date(2024, 6, 15), due_date=date(2024, 7, 15),
                buyer_gstin="29BBBCB5678B2Z6", buyer_name="Test", buyer_address="Addr",
                buyer_state_code="29", place_of_supply="29", place_of_delivery="29",
                status="validated", currency="INR", subtotal=Decimal("1000"),
                total_tax=Decimal("180"), grand_total=Decimal("1180"),
            )
            config = MatchingConfig()
            result = match_invoice_po_grn(invoice, None, None, config)
            assert result.status == MatchStatus.MISSING_PO
        _run_matching_test(_test)

    def test_missing_grn_returns_missing_grn_when_required(self):
        """Missing GRN with require_grn=True should return MISSING_GRN."""
        def _test():
            invoice = Invoice(
                id=1, invoice_number="INV-001", vendor_id=1,
                invoice_date=date(2024, 6, 15), due_date=date(2024, 7, 15),
                buyer_gstin="29BBBCB5678B2Z6", buyer_name="Test", buyer_address="Addr",
                buyer_state_code="29", place_of_supply="29", place_of_delivery="29",
                status="validated", currency="INR", subtotal=Decimal("1000"),
                total_tax=Decimal("180"), grand_total=Decimal("1180"),
            )
            po = PurchaseOrder(
                id=1, po_number="PO-001", vendor_id=1,
                po_date=date(2024, 1, 15), delivery_date=date(2024, 2, 15),
                buyer_gstin="29BBBCB5678B2Z6", buyer_name="Test", buyer_address="Addr",
                buyer_state_code="29", place_of_supply="29",
                status="open", currency="INR", subtotal=Decimal("1000"),
                total_tax=Decimal("180"), grand_total=Decimal("1180"),
            )
            config = MatchingConfig(require_grn=True)
            result = match_invoice_po_grn(invoice, po, None, config)
            assert result.status == MatchStatus.MISSING_GRN
        _run_matching_test(_test)


class TestEvaluateLineMatch:
    """Tests for line match evaluation."""

    def test_matched_status_for_high_similarity(self):
        """High similarity should result in MATCHED status."""
        inv_line = InvoiceLine(
            invoice_id=1, line_number=1, item_code="ITEM1", item_description="Test",
            hsn_code="998713", uom="PCS", quantity=Decimal("100"), unit_price=Decimal("1000"),
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST,
        )
        po_line = POLine(
            po_id=1, line_number=1, item_code="ITEM1", item_description="Test",
            hsn_code="998713", uom="PCS", quantity=Decimal("100"), unit_price=Decimal("1000"),
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST,
        )
        grn_line = GRNLine(
            grn_id=1, line_number=1, po_line_id=1,
            quantity_received=Decimal("100"), quantity_accepted=Decimal("100"), quantity_rejected=Decimal("0"),
        )
        grn_line.po_line = po_line

        config = MatchingConfig()
        result = _evaluate_line_match(inv_line, po_line, grn_line, 95.0, config)
        assert result.status == LineMatchStatus.MATCHED

    def test_price_mismatch_status(self):
        """Price mismatch should result in PRICE_MISMATCH status when GRN exists."""
        inv_line = InvoiceLine(
            invoice_id=1, line_number=1, item_code="ITEM1", item_description="Test",
            hsn_code="998713", uom="PCS", quantity=Decimal("100"), unit_price=Decimal("1500"),  # 50% diff
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST,
        )
        po_line = POLine(
            po_id=1, line_number=1, item_code="ITEM1", item_description="Test",
            hsn_code="998713", uom="PCS", quantity=Decimal("100"), unit_price=Decimal("1000"),
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST,
        )
        # Provide a GRN line so price mismatch can be detected (otherwise MISSING_IN_GRN overrides)
        grn_line = GRNLine(
            grn_id=1, line_number=1, po_line_id=1,
            quantity_received=Decimal("100"), quantity_accepted=Decimal("100"), quantity_rejected=Decimal("0"),
        )
        grn_line.po_line = po_line
        config = MatchingConfig(price_tolerance_pct=2.0)
        result = _evaluate_line_match(inv_line, po_line, grn_line, 80.0, config)
        assert result.status == LineMatchStatus.PRICE_MISMATCH
        assert len(result.discrepancies) > 0
        assert result.discrepancies[0].field == "unit_price"

    def test_missing_grn_overrides_price_mismatch(self):
        """Missing GRN should result in MISSING_IN_GRN even if price mismatch."""
        inv_line = InvoiceLine(
            invoice_id=1, line_number=1, item_code="ITEM1", item_description="Test",
            hsn_code="998713", uom="PCS", quantity=Decimal("100"), unit_price=Decimal("1500"),  # 50% diff
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST,
        )
        po_line = POLine(
            po_id=1, line_number=1, item_code="ITEM1", item_description="Test",
            hsn_code="998713", uom="PCS", quantity=Decimal("100"), unit_price=Decimal("1000"),
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST,
        )
        config = MatchingConfig(price_tolerance_pct=2.0)
        result = _evaluate_line_match(inv_line, po_line, None, 80.0, config)
        assert result.status == LineMatchStatus.MISSING_IN_GRN


class TestCalculateSummary:
    """Tests for summary calculation."""

    def test_counts_line_statuses(self):
        """Summary should count line statuses correctly."""
        result = MatchResult(
            invoice_id=1, invoice_number="INV-001",
            line_matches=[
                LineMatchResult(invoice_line_id=1, invoice_line_number=1, status=LineMatchStatus.MATCHED),
                LineMatchResult(invoice_line_id=2, invoice_line_number=2, status=LineMatchStatus.MATCHED),
                LineMatchResult(invoice_line_id=3, invoice_line_number=3, status=LineMatchStatus.PRICE_MISMATCH),
                LineMatchResult(invoice_line_id=None, invoice_line_number=None, po_line_id=4, po_line_number=4,
                               status=LineMatchStatus.MISSING_IN_PO),  # This is the status for missing PO line
            ],
        )
        invoice = Invoice(
            id=1, invoice_number="INV-001", vendor_id=1,
            invoice_date=date(2024, 6, 15), due_date=date(2024, 7, 15),
            buyer_gstin="29BBBCB5678B2Z6", buyer_name="Test", buyer_address="Addr",
            buyer_state_code="29", place_of_supply="29", place_of_delivery="29",
            status="validated", currency="INR", subtotal=Decimal("1000"),
            total_tax=Decimal("180"), grand_total=Decimal("1180"),
        )
        po = PurchaseOrder(
            id=1, po_number="PO-001", vendor_id=1,
            po_date=date(2024, 1, 15), delivery_date=date(2024, 2, 15),
            buyer_gstin="29BBBCB5678B2Z6", buyer_name="Test", buyer_address="Addr",
            buyer_state_code="29", place_of_supply="29",
            status="open", currency="INR", subtotal=Decimal("1000"),
            total_tax=Decimal("180"), grand_total=Decimal("1180"),
        )
        config = MatchingConfig()
        _calculate_summary(result, invoice, po, None, config)

        assert result.total_lines == 4
        assert result.matched_lines == 2
        assert result.mismatched_lines == 1
        assert result.missing_in_po == 1


class TestDetermineOverallStatus:
    """Tests for overall status determination."""

    def test_all_matched_returns_matched(self):
        """All lines matched should return MATCHED."""
        result = MatchResult(
            invoice_id=1, invoice_number="INV-001",
            total_lines=3, matched_lines=3, mismatched_lines=0,
            partial_lines=0, missing_in_grn=0, missing_in_po=0, extra_in_invoice=0,
        )
        _determine_overall_status(result)
        assert result.status == MatchStatus.MATCHED

    def test_mismatched_lines_returns_mismatch(self):
        """Any mismatched lines should return MISMATCH."""
        result = MatchResult(
            invoice_id=1, invoice_number="INV-001",
            total_lines=3, matched_lines=2, mismatched_lines=1,
            partial_lines=0, missing_in_grn=0, missing_in_po=0, extra_in_invoice=0,
        )
        _determine_overall_status(result)
        assert result.status == MatchStatus.MISMATCH

    def test_partial_lines_returns_partial(self):
        """Partial lines should return PARTIAL."""
        result = MatchResult(
            invoice_id=1, invoice_number="INV-001",
            total_lines=3, matched_lines=2, mismatched_lines=0,
            partial_lines=1, missing_in_grn=0, missing_in_po=0, extra_in_invoice=0,
        )
        _determine_overall_status(result)
        assert result.status == MatchStatus.PARTIAL

    def test_missing_po_returns_missing_po(self):
        """Missing PO should return MISSING_PO."""
        result = MatchResult(
            invoice_id=1, invoice_number="INV-001",
            total_lines=3, matched_lines=0, mismatched_lines=0,
            partial_lines=0, missing_in_grn=0, missing_in_po=3, extra_in_invoice=0,
        )
        _determine_overall_status(result)
        assert result.status == MatchStatus.MISSING_PO
