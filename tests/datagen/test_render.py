"""Tests for PDF rendering."""

import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from datagen.models import Address, BankAccount, Invoice, InvoiceLine, StateCode, TaxType, UoM, Vendor
from datagen.render import WEASYPRINT_AVAILABLE, InvoiceRenderer, render_invoice


class TestInvoiceRenderer:
    """Tests for InvoiceRenderer."""

    @pytest.fixture
    def template_dir(self):
        return Path(__file__).parent.parent.parent / "datagen" / "templates"

    @pytest.fixture
    def sample_vendor(self):
        return Vendor(
            id=UUID("00000000-0000-0000-0000-000000000001"),
            name="Test Vendor Pvt Ltd",
            gstin="29ABCDE1234F1Z5",
            address=Address(line1="123 Test Street", city="Bengaluru", state=StateCode.KA, pincode="560001"),
            bank_account=BankAccount(
                account_number="1234567890123456",
                ifsc="SBIN0001234",
                bank_name="State Bank of India",
                branch="Test Branch",
                account_holder="Test Vendor Pvt Ltd",
            ),
            email="test@vendor.com",
            phone="+91-9876543210",
        )

    @pytest.fixture
    def sample_invoice(self):
        lines = [
            InvoiceLine(
                line_number=1,
                item_code="ITM001",
                item_description="Test Product",
                hsn_code="8471",
                uom=UoM.PCS,
                quantity=Decimal("10"),
                unit_price=Decimal("1000.00"),
                tax_rate=Decimal("0.18"),
                tax_type=TaxType.IGST,
            ),
            InvoiceLine(
                line_number=2,
                item_code="ITM002",
                item_description="Another Product",
                hsn_code="8517",
                uom=UoM.PCS,
                quantity=Decimal("5"),
                unit_price=Decimal("2000.00"),
                tax_rate=Decimal("0.18"),
                tax_type=TaxType.IGST,
            ),
        ]
        invoice = Invoice(
            invoice_number="INV000001",
            invoice_date=date(2024, 1, 15),
            vendor_id=UUID("00000000-0000-0000-0000-000000000001"),
            vendor_gstin="29ABCDE1234F1Z5",
            vendor_name="Test Vendor Pvt Ltd",
            vendor_address=Address(line1="123 Test Street", city="Bengaluru", state=StateCode.KA, pincode="560001"),
            buyer_gstin="29AAAAA0000A1Z5",
            buyer_name="Buyer Corp",
            buyer_address=Address(line1="456 Buyer Ave", city="Mumbai", state=StateCode.MH, pincode="400001"),
            lines=lines,
            place_of_supply=StateCode.KA,
            place_of_delivery=StateCode.KA,
        )
        invoice.compute_totals()
        return invoice

    def test_indian_format_filter(self, template_dir):
        """Test Indian number formatting filter."""
        renderer = InvoiceRenderer(template_dir)
        assert renderer._indian_format(1234567.89) == "12,34,567.89"
        assert renderer._indian_format(12345.67) == "12,345.67"
        assert renderer._indian_format(1000) == "1,000.00"
        assert renderer._indian_format(100) == "100.00"

    def test_amount_in_words(self, template_dir):
        """Test amount in words filter."""
        renderer = InvoiceRenderer(template_dir)
        words = renderer._amount_in_words(1234567.89)
        assert "Twelve Lakh" in words or "Lakh" in words
        assert "Only" in words

    def test_render_html(self, template_dir, sample_vendor, sample_invoice):
        """Test HTML rendering."""
        renderer = InvoiceRenderer(template_dir)
        html = renderer.render_html("template_01_standard", sample_invoice, sample_vendor)
        assert "INV000001" in html
        assert "Test Vendor Pvt Ltd" in html
        assert "Test Product" in html
        # Check Indian format is used (values with commas)
        assert "10,000.00" in html or "20,000.00" in html or "1,000.00" in html

    def test_render_all_templates(self, template_dir, sample_vendor, sample_invoice):
        """Test all templates can be rendered."""
        renderer = InvoiceRenderer(template_dir)
        templates = renderer.get_template_names()
        assert len(templates) >= 8

        for template in templates:
            html = renderer.render_html(template, sample_invoice, sample_vendor)
            assert "INV000001" in html
            assert len(html) > 1000

    @pytest.mark.skipif(not WEASYPRINT_AVAILABLE, reason="WeasyPrint not available")
    def test_render_pdf(self, template_dir, sample_vendor, sample_invoice):
        """Test PDF rendering."""
        renderer = InvoiceRenderer(template_dir)
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.pdf"
            html = renderer.render_html("template_01_standard", sample_invoice, sample_vendor)
            renderer.render_pdf(html, output_path)
            assert output_path.exists()
            assert output_path.stat().st_size > 0

    @pytest.mark.skipif(not WEASYPRINT_AVAILABLE, reason="WeasyPrint not available")
    def test_render_invoice_high_level(self, template_dir, sample_vendor, sample_invoice):
        """Test high-level render_invoice function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "invoice.pdf"
            render_invoice(
                template_name="template_01_standard",
                invoice=sample_invoice,
                vendor=sample_vendor,
                output_path=output_path,
                template_dir=template_dir,
                degrade=False,
            )
            assert output_path.exists()
            assert output_path.stat().st_size > 0

    def test_bilingual_templates(self, template_dir, sample_vendor, sample_invoice):
        """Test bilingual templates render correctly."""
        renderer = InvoiceRenderer(template_dir)

        # Hindi template
        html = renderer.render_html("template_07_bilingual_hi", sample_invoice, sample_vendor)
        assert "कर चालान" in html or "Tax" in html

        # Kannada template
        html = renderer.render_html("template_08_bilingual_kn", sample_invoice, sample_vendor)
        assert "ತೆರಿಗೆ" in html or "Tax" in html


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
