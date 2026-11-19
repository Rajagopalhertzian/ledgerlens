"""Property-based tests for tax validation (V3, V4, V5)."""

from decimal import Decimal
from hypothesis import given, strategies as st, settings
from hypothesis.strategies import integers, decimals, text, sampled_from

from ledgerlens.validation.tax import (
    validate_tax_type_vs_places,
    validate_line_tax_arithmetic,
    validate_invoice_totals,
    validate_po_line_arithmetic,
    validate_grn_line_quantities,
)
from ledgerlens.db.models import Invoice, InvoiceLine, POLine, GRNLine, TaxType


# Strategies for generating test data
@st.composite
def positive_decimal(draw, min_val="0.01", max_val="100000", places=2):
    """Generate positive decimal values."""
    return draw(decimals(min_value=min_val, max_value=max_val, places=places))


@st.composite
def tax_rate_strategy(draw):
    """Generate valid GST tax rates."""
    return draw(sampled_from([Decimal("0"), Decimal("5"), Decimal("12"), Decimal("18"), Decimal("28")]))


@st.composite
def tax_type_strategy(draw):
    """Generate valid tax types."""
    return draw(sampled_from([TaxType.CGST, TaxType.SGST, TaxType.IGST, TaxType.CESS]))


@st.composite
def invoice_line_strategy(draw):
    """Generate a valid InvoiceLine for testing."""
    return InvoiceLine(
        invoice_id=1,
        line_number=draw(integers(min_value=1, max_value=100)),
        item_code=draw(text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", min_size=1, max_size=20)),
        item_description=draw(text(min_size=1, max_size=100)),
        hsn_code=draw(text(alphabet="0123456789", min_size=4, max_size=8)),
        uom=draw(sampled_from(["PCS", "KG", "MTR", "LTR", "BOX"])),
        quantity=draw(positive_decimal("1", "1000")),
        unit_price=draw(positive_decimal("1", "10000")),
        discount_percent=draw(decimals(min_value=0, max_value=50, places=2)),
        tax_rate=draw(tax_rate_strategy()),
        tax_type=draw(tax_type_strategy()),
        taxable_value=None,  # Will be calculated
        tax_amount=None,
        line_total=None,
    )


class TestTaxTypeVsPlaces:
    """V3: Tax type vs places of supply validation."""

    def test_intra_state_requires_cgst_sgst(self):
        """Intra-state invoices should have CGST or SGST."""
        invoice = Invoice(
            place_of_supply="29",
            place_of_delivery="29",
        )
        line = InvoiceLine(
            invoice_id=1, line_number=1, item_code="ITEM1", item_description="Test",
            hsn_code="998713", uom="PCS", quantity=Decimal("10"), unit_price=Decimal("100"),
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.CGST,
            taxable_value=Decimal("1000"), tax_amount=Decimal("180"), line_total=Decimal("1180")
        )
        results = validate_tax_type_vs_places(invoice, [line])
        assert len(results) == 1
        assert results[0].passed

    def test_inter_state_requires_igst(self):
        """Inter-state invoices should have IGST."""
        invoice = Invoice(
            place_of_supply="29",
            place_of_delivery="27",
        )
        line = InvoiceLine(
            invoice_id=1, line_number=1, item_code="ITEM1", item_description="Test",
            hsn_code="998713", uom="PCS", quantity=Decimal("10"), unit_price=Decimal("100"),
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST,
            taxable_value=Decimal("1000"), tax_amount=Decimal("180"), line_total=Decimal("1180")
        )
        results = validate_tax_type_vs_places(invoice, [line])
        assert len(results) == 1
        assert results[0].passed

    def test_wrong_tax_type_fails(self):
        """Wrong tax type for place of supply should fail."""
        invoice = Invoice(
            place_of_supply="29",
            place_of_delivery="29",  # Intra-state
        )
        line = InvoiceLine(
            invoice_id=1, line_number=1, item_code="ITEM1", item_description="Test",
            hsn_code="998713", uom="PCS", quantity=Decimal("10"), unit_price=Decimal("100"),
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST,  # Wrong for intra
            taxable_value=Decimal("1000"), tax_amount=Decimal("180"), line_total=Decimal("1180")
        )
        results = validate_tax_type_vs_places(invoice, [line])
        assert len(results) == 1
        assert not results[0].passed

    def test_missing_tax_type_fails(self):
        """Missing tax type should fail."""
        invoice = Invoice(place_of_supply="29", place_of_delivery="29")
        line = InvoiceLine(
            invoice_id=1, line_number=1, item_code="ITEM1", item_description="Test",
            hsn_code="998713", uom="PCS", quantity=Decimal("10"), unit_price=Decimal("100"),
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=None,
            taxable_value=Decimal("1000"), tax_amount=Decimal("180"), line_total=Decimal("1180")
        )
        results = validate_tax_type_vs_places(invoice, [line])
        assert len(results) == 1
        assert not results[0].passed


class TestLineTaxArithmetic:
    """V4: Property-based tests for line-level tax arithmetic."""

    @given(
        quantity=positive_decimal("1", "1000"),
        unit_price=positive_decimal("1", "10000"),
        discount_percent=decimals(min_value=0, max_value=50, places=2),
        tax_rate=tax_rate_strategy(),
    )
    @settings(max_examples=100)
    def test_taxable_value_calculation(
        self,
        quantity: Decimal,
        unit_price: Decimal,
        discount_percent: Decimal,
        tax_rate: Decimal,
    ):
        """Taxable value = qty * price * (1 - discount/100)."""
        # Calculate expected values
        taxable = quantity * unit_price * (Decimal("1") - discount_percent / Decimal("100"))
        tax = taxable * tax_rate / Decimal("100")
        line_total = taxable + tax

        line = InvoiceLine(
            invoice_id=1, line_number=1, item_code="ITEM1", item_description="Test",
            hsn_code="998713", uom="PCS", quantity=quantity, unit_price=unit_price,
            discount_percent=discount_percent, tax_rate=tax_rate, tax_type=TaxType.IGST,
            taxable_value=taxable.quantize(Decimal("0.01")),
            tax_amount=tax.quantize(Decimal("0.01")),
            line_total=line_total.quantize(Decimal("0.01")),
        )
        results = validate_line_tax_arithmetic(line)
        # Should have results for taxable, tax, and total
        assert len(results) >= 1
        # All should pass since we provided correct values
        for r in results:
            assert r.passed, f"Validation failed: {r.message}"

    @given(
        quantity=positive_decimal("1", "100"),
        unit_price=positive_decimal("1", "1000"),
        tax_rate=tax_rate_strategy(),
    )
    @settings(max_examples=50)
    def test_zero_discount_calculation(self, quantity: Decimal, unit_price: Decimal, tax_rate: Decimal):
        """With zero discount, taxable = qty * price."""
        line = InvoiceLine(
            invoice_id=1, line_number=1, item_code="ITEM1", item_description="Test",
            hsn_code="998713", uom="PCS", quantity=quantity, unit_price=unit_price,
            discount_percent=Decimal("0"), tax_rate=tax_rate, tax_type=TaxType.IGST,
            taxable_value=quantity * unit_price,  # Correct value
            tax_amount=(quantity * unit_price * tax_rate / Decimal("100")).quantize(Decimal("0.01")),
            line_total=(quantity * unit_price * (Decimal("1") + tax_rate / Decimal("100"))).quantize(Decimal("0.01")),
        )
        results = validate_line_tax_arithmetic(line)
        # All should pass
        for r in results:
            assert r.passed, f"Validation failed: {r.message}"

    def test_cgst_sgst_split(self):
        """For CGST/SGST, each should be half of total tax."""
        line = InvoiceLine(
            invoice_id=1, line_number=1, item_code="ITEM1", item_description="Test",
            hsn_code="998713", uom="PCS", quantity=Decimal("10"), unit_price=Decimal("100"),
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.CGST,
            taxable_value=Decimal("1000"),
            tax_amount=Decimal("180"),
            cgst_amount=Decimal("90"),
            sgst_amount=Decimal("90"),
            igst_amount=Decimal("0"),
            cess_amount=Decimal("0"),
            line_total=Decimal("1180"),
        )
        results = validate_line_tax_arithmetic(line)
        # Find the CGST/SGST check
        cgst_sgst_result = [r for r in results if "CGST" in r.message and "SGST" in r.message]
        assert len(cgst_sgst_result) == 1
        assert cgst_sgst_result[0].passed

    def test_wrong_cgst_sgst_fails(self):
        """Incorrect CGST/SGST split should fail."""
        line = InvoiceLine(
            invoice_id=1, line_number=1, item_code="ITEM1", item_description="Test",
            hsn_code="998713", uom="PCS", quantity=Decimal("10"), unit_price=Decimal("100"),
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.CGST,
            taxable_value=Decimal("1000"),
            tax_amount=Decimal("180"),
            cgst_amount=Decimal("100"),  # Wrong - should be 90
            sgst_amount=Decimal("80"),   # Wrong - should be 90
            igst_amount=Decimal("0"),
            cess_amount=Decimal("0"),
            line_total=Decimal("1180"),
        )
        results = validate_line_tax_arithmetic(line)
        cgst_sgst_result = [r for r in results if "CGST" in r.message and "SGST" in r.message]
        assert len(cgst_sgst_result) == 1
        assert not cgst_sgst_result[0].passed


class TestInvoiceTotals:
    """V5: Property-based tests for invoice totals and rounding."""

    def test_grand_total_calculation(self):
        """Grand total = subtotal + total_tax."""
        subtotal = Decimal("10000")
        total_tax = Decimal("1800")
        grand_total = subtotal + total_tax
        invoice = Invoice(
            subtotal=subtotal,
            total_tax=total_tax,
            grand_total=grand_total,
        )
        lines = [
            InvoiceLine(
                invoice_id=1, line_number=1, item_code="ITEM1", item_description="Test",
                hsn_code="998713", uom="PCS", quantity=Decimal("100"),
                unit_price=Decimal("100"),
                discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST,
                taxable_value=subtotal,
                tax_amount=total_tax,
                line_total=grand_total,
            )
        ]
        results = validate_invoice_totals(invoice, lines)
        # Find grand total check - there may be multiple (subtotal+tax check and rounding check)
        grand_total_results = [r for r in results if "Grand total" in r.message]
        assert len(grand_total_results) >= 1
        # At least one should be the subtotal+tax check and pass
        subtotal_check = [r for r in grand_total_results if "vs subtotal+tax" in r.message]
        assert len(subtotal_check) == 1
        assert subtotal_check[0].passed

    def test_wrong_grand_total_fails(self):
        """Incorrect grand total should fail."""
        invoice = Invoice(
            subtotal=Decimal("1000"),
            total_tax=Decimal("180"),
            grand_total=Decimal("1200"),  # Wrong - should be 1180
        )
        lines = [
            InvoiceLine(
                invoice_id=1, line_number=1, item_code="ITEM1", item_description="Test",
                hsn_code="998713", uom="PCS", quantity=Decimal("10"),
                unit_price=Decimal("100"),
                discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST,
                taxable_value=Decimal("1000"),
                tax_amount=Decimal("180"),
                line_total=Decimal("1200"),
            )
        ]
        results = validate_invoice_totals(invoice, lines)
        grand_total_result = [r for r in results if "Grand total" in r.message and "vs subtotal+tax" in r.message]
        assert len(grand_total_result) >= 1
        assert not grand_total_result[0].passed

    def test_rounding_to_nearest_rupee(self):
        """Indian rounding: grand total should be rounded to nearest rupee."""
        invoice = Invoice(
            subtotal=Decimal("1000.50"),
            total_tax=Decimal("180.45"),
            grand_total=Decimal("1180.95"),  # Not rounded
        )
        lines = [
            InvoiceLine(
                invoice_id=1, line_number=1, item_code="ITEM1", item_description="Test",
                hsn_code="998713", uom="PCS", quantity=Decimal("1"), unit_price=Decimal("1000.50"),
                discount_percent=Decimal("0"), tax_rate=Decimal("0"), tax_type=TaxType.IGST,
                taxable_value=Decimal("1000.50"), tax_amount=Decimal("180.45"), line_total=Decimal("1180.95"),
            )
        ]
        results = validate_invoice_totals(invoice, lines)
        rounding_result = [r for r in results if "rounded" in r.message.lower()]
        assert len(rounding_result) >= 1
        assert not rounding_result[0].passed

    def test_properly_rounded_passes(self):
        """Properly rounded grand total should pass."""
        invoice = Invoice(
            subtotal=Decimal("1000"),
            total_tax=Decimal("180"),
            grand_total=Decimal("1180"),  # Already rounded
        )
        lines = [
            InvoiceLine(
                invoice_id=1, line_number=1, item_code="ITEM1", item_description="Test",
                hsn_code="998713", uom="PCS", quantity=Decimal("1"), unit_price=Decimal("1000"),
                discount_percent=Decimal("0"), tax_rate=Decimal("0"), tax_type=TaxType.IGST,
                taxable_value=Decimal("1000"), tax_amount=Decimal("180"), line_total=Decimal("1180"),
            )
        ]
        results = validate_invoice_totals(invoice, lines)
        rounding_result = [r for r in results if "rounded" in r.message.lower()]
        assert len(rounding_result) >= 1
        assert rounding_result[0].passed


class TestPOLineArithmetic:
    """Tests for PO line arithmetic validation."""

    def test_po_line_calculation_matches_invoice(self):
        """PO line arithmetic should follow same rules as invoice."""
        po_line = POLine(
            po_id=1, line_number=1, item_code="ITEM1", item_description="Test",
            hsn_code="998713", uom="PCS", quantity=Decimal("10"), unit_price=Decimal("100"),
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST,
            taxable_value=Decimal("1000"), tax_amount=Decimal("180"), line_total=Decimal("1180"),
        )
        results = validate_po_line_arithmetic(po_line)
        for r in results:
            assert r.passed, f"PO line validation failed: {r.message}"


class TestGRNLineQuantities:
    """Tests for GRN line quantity validation."""

    def test_received_not_greater_than_po(self):
        """GRN received quantity should not exceed PO quantity."""
        po_line = POLine(
            po_id=1, line_number=1, item_code="ITEM1", item_description="Test",
            hsn_code="998713", uom="PCS", quantity=Decimal("100"), unit_price=Decimal("100"),
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST,
            taxable_value=Decimal("10000"), tax_amount=Decimal("1800"), line_total=Decimal("11800"),
        )
        # Valid: received <= PO qty
        grn_line = GRNLine(
            grn_id=1, line_number=1, po_line_id=1,
            quantity_received=Decimal("100"), quantity_accepted=Decimal("100"), quantity_rejected=Decimal("0"),
        )
        results = validate_grn_line_quantities(grn_line, po_line)
        assert all(r.passed for r in results)

    def test_received_greater_than_po_fails(self):
        """GRN received > PO qty should fail."""
        po_line = POLine(
            po_id=1, line_number=1, item_code="ITEM1", item_description="Test",
            hsn_code="998713", uom="PCS", quantity=Decimal("100"), unit_price=Decimal("100"),
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST,
            taxable_value=Decimal("10000"), tax_amount=Decimal("1800"), line_total=Decimal("11800"),
        )
        grn_line = GRNLine(
            grn_id=1, line_number=1, po_line_id=1,
            quantity_received=Decimal("150"), quantity_accepted=Decimal("100"), quantity_rejected=Decimal("0"),
        )
        results = validate_grn_line_quantities(grn_line, po_line)
        assert any(not r.passed for r in results)

    def test_accepted_plus_rejected_equals_received(self):
        """Accepted + Rejected must equal Received."""
        po_line = POLine(
            po_id=1, line_number=1, item_code="ITEM1", item_description="Test",
            hsn_code="998713", uom="PCS", quantity=Decimal("100"), unit_price=Decimal("100"),
            discount_percent=Decimal("0"), tax_rate=Decimal("18"), tax_type=TaxType.IGST,
            taxable_value=Decimal("10000"), tax_amount=Decimal("1800"), line_total=Decimal("11800"),
        )
        # Invalid: accepted + rejected != received
        grn_line = GRNLine(
            grn_id=1, line_number=1, po_line_id=1,
            quantity_received=Decimal("100"), quantity_accepted=Decimal("80"), quantity_rejected=Decimal("10"),
        )
        results = validate_grn_line_quantities(grn_line, po_line)
        assert any(not r.passed for r in results)
