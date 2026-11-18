"""Tests for synthetic data generation."""

import json
import tempfile
from pathlib import Path

import pytest

from datagen.generate import DataGenerator
from datagen.models import (
    DefectType,
)
from datagen.utils import (
    generate_goods_receipt,
    generate_invoice,
    generate_purchase_order,
    generate_vendor,
    get_template_for_invoice,
)


class TestVendorGeneration:
    """Tests for vendor generation."""

    def test_generate_vendor_has_valid_gstin(self):
        """Generated vendor should have valid GSTIN."""
        import random
        rng = random.Random(42)
        vendor = generate_vendor(rng)
        assert vendor.gstin is not None
        assert len(vendor.gstin) == 15

    def test_generate_vendor_has_address(self):
        """Generated vendor should have address."""
        import random
        rng = random.Random(42)
        vendor = generate_vendor(rng)
        assert vendor.address is not None
        assert vendor.address.line1
        assert vendor.address.city
        assert vendor.address.state
        assert vendor.address.pincode

    def test_generate_vendor_has_bank_account(self):
        """Generated vendor should have bank account."""
        import random
        rng = random.Random(42)
        vendor = generate_vendor(rng)
        assert vendor.bank_account is not None
        assert vendor.bank_account.account_number
        assert vendor.bank_account.ifsc
        assert vendor.bank_account.bank_name

    def test_generate_vendor_deterministic(self):
        """Same seed should produce same vendor."""
        import random
        rng1 = random.Random(42)
        rng2 = random.Random(42)
        v1 = generate_vendor(rng1)
        v2 = generate_vendor(rng2)
        assert v1.gstin == v2.gstin
        assert v1.name == v2.name


class TestPOGeneration:
    """Tests for purchase order generation."""

    def test_generate_purchase_order(self):
        """Should generate valid PO."""
        import random
        rng = random.Random(42)
        vendor = generate_vendor(rng)
        po = generate_purchase_order(rng, vendor, 1)
        assert po.po_number == "PO000001"
        assert po.vendor_id == vendor.id
        assert po.vendor_gstin == vendor.gstin
        assert len(po.lines) >= 1
        assert po.subtotal > 0
        assert po.grand_total > 0

    def test_po_line_calculations(self):
        """PO line calculations should be correct."""
        import random
        from decimal import Decimal
        rng = random.Random(42)
        vendor = generate_vendor(rng)
        po = generate_purchase_order(rng, vendor, 1)
        for line in po.lines:
            taxable = line.quantity * line.unit_price * (Decimal("1") - line.discount_percent / Decimal("100"))
            assert abs(line.taxable_value - taxable) < Decimal("0.01")
            assert abs(line.tax_amount - (taxable * line.tax_rate)) < Decimal("0.01")
            assert abs(line.line_total - (line.taxable_value + line.tax_amount)) < Decimal("0.01")


class TestGRNGeneration:
    """Tests for goods receipt generation."""

    def test_generate_goods_receipt(self):
        """Should generate valid GRN."""
        import random
        rng = random.Random(42)
        vendor = generate_vendor(rng)
        po = generate_purchase_order(rng, vendor, 1)
        grn = generate_goods_receipt(rng, po, 1)
        assert grn.grn_number == "GRN000001"
        assert grn.po_id == po.id
        assert grn.vendor_id == po.vendor_id
        assert len(grn.lines) == len(po.lines)

    def test_grn_partial_delivery(self):
        """GRN should have partial delivery quantities."""
        import random
        rng = random.Random(42)
        vendor = generate_vendor(rng)
        po = generate_purchase_order(rng, vendor, 1)
        grn = generate_goods_receipt(rng, po, 1)
        for grn_line, po_line in zip(grn.lines, po.lines, strict=False):
            # Should be within 80-120% of ordered
            ratio = grn_line.received_quantity / po_line.quantity
            assert 0.75 <= ratio <= 1.25


class TestInvoiceGeneration:
    """Tests for invoice generation."""

    def test_generate_invoice_with_po(self):
        """Should generate invoice linked to PO."""
        import random
        rng = random.Random(42)
        vendor = generate_vendor(rng)
        po = generate_purchase_order(rng, vendor, 1)
        grn = generate_goods_receipt(rng, po, 1)
        invoice = generate_invoice(rng, vendor, po, grn, 1, "template_01_standard", DefectType.D01, True)
        assert invoice.invoice_number == "INV000001"
        assert invoice.vendor_id == vendor.id
        assert invoice.po_reference == po.po_number
        assert invoice.grn_reference == grn.grn_number
        assert len(invoice.lines) > 0

    def test_generate_invoice_without_po(self):
        """Should generate invoice without PO."""
        import random
        rng = random.Random(42)
        vendor = generate_vendor(rng)
        invoice = generate_invoice(rng, vendor, None, None, 1, "template_01_standard", DefectType.D01, True)
        assert invoice.po_reference is None
        assert invoice.grn_reference is None
        assert len(invoice.lines) > 0

    def test_invoice_totals_calculated(self):
        """Invoice totals should be calculated correctly."""
        import random
        from decimal import Decimal
        rng = random.Random(42)
        vendor = generate_vendor(rng)
        po = generate_purchase_order(rng, vendor, 1)
        invoice = generate_invoice(rng, vendor, po, None, 1, "template_01_standard", DefectType.D01, True)
        assert invoice.subtotal > 0
        assert invoice.total_tax > 0
        assert invoice.grand_total > 0
        assert abs(invoice.grand_total - (invoice.subtotal + invoice.total_tax)) < Decimal("0.01")


class TestDefectApplication:
    """Tests for defect application."""

    def test_d01_clean_no_defects(self):
        """D01 should have no defects."""
        import random
        rng = random.Random(42)
        vendor = generate_vendor(rng)
        po = generate_purchase_order(rng, vendor, 1)
        invoice = generate_invoice(rng, vendor, po, None, 1, "template_01_standard", DefectType.D01, True)
        assert len(invoice.defects) == 1
        assert invoice.defects[0].type == DefectType.D01

    def test_d02_price_variance(self):
        """D02 should have price variance."""
        import random
        rng = random.Random(42)
        vendor = generate_vendor(rng)
        po = generate_purchase_order(rng, vendor, 1)
        invoice = generate_invoice(rng, vendor, po, None, 1, "template_01_standard", DefectType.D02, True)
        defect_types = {d.type for d in invoice.defects}
        assert DefectType.D02 in defect_types

    def test_d03_over_billing(self):
        """D03 should have quantity exceeding GRN."""
        import random
        rng = random.Random(42)
        vendor = generate_vendor(rng)
        po = generate_purchase_order(rng, vendor, 1)
        grn = generate_goods_receipt(rng, po, 1)
        invoice = generate_invoice(rng, vendor, po, grn, 1, "template_01_standard", DefectType.D03, True)
        defect_types = {d.type for d in invoice.defects}
        assert DefectType.D03 in defect_types

    def test_d04_no_grn(self):
        """D04 should have no GRN reference."""
        import random
        rng = random.Random(42)
        vendor = generate_vendor(rng)
        po = generate_purchase_order(rng, vendor, 1)
        grn = generate_goods_receipt(rng, po, 1)
        invoice = generate_invoice(rng, vendor, po, grn, 1, "template_01_standard", DefectType.D04, True)
        assert invoice.grn_reference is None
        defect_types = {d.type for d in invoice.defects}
        assert DefectType.D04 in defect_types

    def test_d09_invalid_gstin(self):
        """D09 should have invalid GSTIN."""
        import random
        rng = random.Random(42)
        vendor = generate_vendor(rng)
        po = generate_purchase_order(rng, vendor, 1)
        invoice = generate_invoice(rng, vendor, po, None, 1, "template_01_standard", DefectType.D09, True)
        assert not invoice.vendor_gstin.startswith("29") or "INVALID" in invoice.vendor_gstin
        defect_types = {d.type for d in invoice.defects}
        assert DefectType.D09 in defect_types


class TestTemplateSelection:
    """Tests for template selection."""

    def test_first_100_use_template_01(self):
        """First 100 invoices should use template_01."""
        import random
        rng = random.Random(42)
        for i in range(100):
            template = get_template_for_invoice(rng, i)
            assert template == "template_01_standard"

    def test_after_100_uses_various(self):
        """After 100 should use various templates."""
        import random
        rng = random.Random(42)
        templates = set()
        for i in range(100, 200):
            templates.add(get_template_for_invoice(rng, i))
        assert len(templates) > 1


class TestDataGenerator:
    """Tests for the main DataGenerator class."""

    def test_full_generation_pipeline(self):
        """Test the full generation pipeline with small numbers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "test_data"
            generator = DataGenerator(seed=42, output_dir=output_dir)

            # Override counts for faster test
            generator.generate_vendors(5)
            generator.generate_purchase_orders(10)
            generator.generate_goods_receipts()
            generator.generate_invoices(20)

            assert len(generator.vendors) == 5
            assert len(generator.purchase_orders) == 10
            assert len(generator.invoices) == 20

            # Check splits
            total_split = sum(s.count for s in generator.splits.values())
            assert total_split == 20

    def test_manifest_generation(self):
        """Test manifest is generated with hashes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "test_data"
            generator = DataGenerator(seed=42, output_dir=output_dir)
            generator.generate_vendors(2)
            generator.generate_purchase_orders(2)
            generator.generate_goods_receipts()
            generator.generate_invoices(5)
            generator.render_invoices()
            generator.write_ground_truth()
            generator.write_manifest()

            manifest_path = output_dir / "manifest.json"
            assert manifest_path.exists()

            with open(manifest_path) as f:
                manifest = json.load(f)

            assert manifest["seed"] == 42
            assert "files" in manifest
            assert len(manifest["files"]) > 0

    def test_deterministic_generation(self):
        """Same seed should produce identical output."""
        with tempfile.TemporaryDirectory() as tmpdir1:
            output_dir1 = Path(tmpdir1) / "data"
            gen1 = DataGenerator(seed=42, output_dir=output_dir1)
            gen1.generate_vendors(3)
            gen1.generate_purchase_orders(5)
            gen1.generate_goods_receipts()
            gen1.generate_invoices(10)

        with tempfile.TemporaryDirectory() as tmpdir2:
            output_dir2 = Path(tmpdir2) / "data"
            gen2 = DataGenerator(seed=42, output_dir=output_dir2)
            gen2.generate_vendors(3)
            gen2.generate_purchase_orders(5)
            gen2.generate_goods_receipts()
            gen2.generate_invoices(10)

            # Compare invoice numbers
            inv_nums1 = {inv.invoice_number for inv in gen1.invoices}
            inv_nums2 = {inv.invoice_number for inv in gen2.invoices}
            assert inv_nums1 == inv_nums2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
