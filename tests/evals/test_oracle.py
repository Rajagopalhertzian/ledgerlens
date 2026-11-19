"""Tests for oracle baseline evaluation."""

import json

import pytest

from datagen.models import Decision, Defect, DefectType, GroundTruth
from evals.run_oracle import decide_invoice, run_oracle, validate_duplicate, validate_gst_rules, validate_tax_arithmetic


class TestOracleValidators:
    """Tests for oracle validators."""

    def make_ground_truth(self, overrides: dict | None = None) -> GroundTruth:
        """Create a sample ground truth."""
        base = {
            "invoice_id": "00000000-0000-0000-0000-000000000001",
            "invoice_number": "INV000001",
            "vendor_id": "00000000-0000-0000-0000-000000000002",
            "vendor_gstin": "29ABCDE1234F1Z5",
            "header": {
                "invoice_number": "INV000001",
                "invoice_date": "2024-01-15",
                "vendor_gstin": "29ABCDE1234F1Z5",
                "vendor_name": "Test Vendor",
                "buyer_gstin": "29AAAAA0000A1Z5",
                "buyer_name": "Buyer",
                "place_of_supply": "29",
                "place_of_delivery": "29",
            },
            "lines": [
                {
                    "line_number": 1,
                    "item_code": "ITM001",
                    "item_description": "Test Item",
                    "hsn_code": "8471",
                    "uom": "PCS",
                    "quantity": "10",
                    "unit_price": "1000.00",
                    "tax_rate": "0.18",
                    "tax_type": "IGST",
                    "discount_percent": "0",
                    "taxable_value": "10000.00",
                    "tax_amount": "1800.00",
                    "line_total": "11800.00",
                }
            ],
            "taxes": {"cgst": "0", "sgst": "0", "igst": "1800.00", "cess": "0"},
            "totals": {"subtotal": "10000.00", "total_tax": "1800.00", "grand_total": "11800.00"},
            "expected_decision": Decision.POST,
            "defects": [Defect(type=DefectType.D01)],
            "expected_actions": [],
        }
        if overrides:
            base.update(overrides)
        return GroundTruth(**base)

    def test_validate_tax_arithmetic_clean(self):
        """Clean invoice should pass tax validation."""
        gt = self.make_ground_truth()
        errors = validate_tax_arithmetic(gt)
        assert len(errors) == 0

    def test_validate_tax_arithmetic_error(self):
        """Wrong line total should be caught."""
        gt = self.make_ground_truth(
            {
                "lines": [
                    {
                        "line_number": 1,
                        "item_code": "ITM001",
                        "item_description": "Test Item",
                        "hsn_code": "8471",
                        "uom": "PCS",
                        "quantity": "10",
                        "unit_price": "1000.00",
                        "tax_rate": "0.18",
                        "tax_type": "IGST",
                        "discount_percent": "0",
                        "taxable_value": "10000.00",
                        "tax_amount": "1800.00",
                        "line_total": "12000.00",  # Wrong
                    }
                ],
                "totals": {"subtotal": "10000.00", "total_tax": "1800.00", "grand_total": "11800.00"},
            }
        )
        errors = validate_tax_arithmetic(gt)
        assert len(errors) > 0
        assert "line total mismatch" in errors[0]

    def test_validate_gst_rules_intra_state(self):
        """Intra-state should use CGST+SGST."""
        gt = self.make_ground_truth(
            {
                "header": {**self.make_ground_truth().header, "place_of_supply": "29", "place_of_delivery": "29"},
                "lines": [
                    {
                        **self.make_ground_truth().lines[0],
                        "tax_type": "IGST",  # Wrong for intra-state
                    }
                ],
            }
        )
        errors = validate_gst_rules(gt)
        assert len(errors) > 0
        assert "Intrastate supply should use CGST+SGST" in errors[0]

    def test_validate_gst_rules_inter_state(self):
        """Inter-state should use IGST."""
        gt = self.make_ground_truth(
            {
                "header": {**self.make_ground_truth().header, "place_of_supply": "29", "place_of_delivery": "27"},
                "lines": [
                    {
                        **self.make_ground_truth().lines[0],
                        "tax_type": "CGST",  # Wrong for inter-state
                    }
                ],
            }
        )
        errors = validate_gst_rules(gt)
        assert len(errors) > 0
        assert "Interstate supply should use IGST" in errors[0]

    def test_validate_duplicate(self):
        """Should detect exact duplicates."""
        gt1 = self.make_ground_truth({"invoice_number": "INV001"})
        gt2 = self.make_ground_truth({"invoice_number": "INV001"})  # Same number

        seen = {}
        errors1 = validate_duplicate(gt1, seen)
        errors2 = validate_duplicate(gt2, seen)

        assert len(errors1) == 0
        assert len(errors2) > 0
        assert "Exact duplicate" in errors2[0]


class TestOracleDecision(TestOracleValidators):
    """Tests for oracle decision logic."""

    def test_clean_invoice_posts(self):
        """Clean invoice (D01 only) should POST."""
        gt = self.make_ground_truth({"defects": [Defect(type=DefectType.D01)]})
        seen = {}
        decision = decide_invoice(gt, seen, [], {})
        assert decision == Decision.POST

    def test_exact_duplicate_rejects(self):
        """Exact duplicate (D05) should REJECT."""
        gt = self.make_ground_truth({"defects": [Defect(type=DefectType.D05)]})
        seen = {}
        decision = decide_invoice(gt, seen, [], {})
        assert decision == Decision.REJECT

    def test_illegible_rejects(self):
        """Illegible (D14) should REJECT."""
        gt = self.make_ground_truth({"defects": [Defect(type=DefectType.D14)]})
        seen = {}
        decision = decide_invoice(gt, seen, [], {})
        assert decision == Decision.REJECT

    def test_near_duplicate_escalates(self):
        """Near duplicate (D06) should ESCALATE."""
        gt = self.make_ground_truth({"defects": [Defect(type=DefectType.D06)]})
        seen = {}
        decision = decide_invoice(gt, seen, [], {})
        assert decision == Decision.ESCALATE

    def test_invalid_gstin_escalates(self):
        """Invalid GSTIN (D09) should ESCALATE."""
        gt = self.make_ground_truth({"defects": [Defect(type=DefectType.D09)]})
        seen = {}
        decision = decide_invoice(gt, seen, [], {})
        assert decision == Decision.ESCALATE

    def test_bank_change_escalates(self):
        """Bank detail change (D10) should ESCALATE."""
        gt = self.make_ground_truth({"defects": [Defect(type=DefectType.D10)]})
        seen = {}
        decision = decide_invoice(gt, seen, [], {})
        assert decision == Decision.ESCALATE

    def test_policy_violation_escalates(self):
        """Policy violation (D15) should ESCALATE."""
        gt = self.make_ground_truth({"defects": [Defect(type=DefectType.D15)]})
        seen = {}
        decision = decide_invoice(gt, seen, [], {})
        assert decision == Decision.ESCALATE

    def test_price_variance_investigates(self):
        """Price variance (D02) should INVESTIGATE."""
        gt = self.make_ground_truth({"defects": [Defect(type=DefectType.D02)]})
        seen = {}
        decision = decide_invoice(gt, seen, [], {})
        assert decision == Decision.INVESTIGATE

    def test_over_billing_investigates(self):
        """Over-billing (D03) should INVESTIGATE."""
        gt = self.make_ground_truth({"defects": [Defect(type=DefectType.D03)]})
        seen = {}
        decision = decide_invoice(gt, seen, [], {})
        assert decision == Decision.INVESTIGATE


class TestRunOracle:
    """Integration tests for run_oracle."""

    def test_run_oracle_on_sample(self, tmp_path):
        """Test oracle on a few sample ground truths."""
        gt_dir = tmp_path / "ground_truth"
        gt_dir.mkdir()
        output_dir = tmp_path / "results"

        # Create sample ground truths
        for i in range(5):
            gt = {
                "invoice_id": f"00000000-0000-0000-0000-{i:012d}",
                "invoice_number": f"INV{i:06d}",
                "vendor_id": "00000000-0000-0000-0000-000000000002",
                "vendor_gstin": "29ABCDE1234F1Z5",
                "header": {
                    "invoice_number": f"INV{i:06d}",
                    "invoice_date": "2024-01-15",
                    "vendor_gstin": "29ABCDE1234F1Z5",
                    "vendor_name": "Test Vendor",
                    "buyer_gstin": "29AAAAA0000A1Z5",
                    "buyer_name": "Buyer",
                    "place_of_supply": "29",
                    "place_of_delivery": "29",
                },
                "lines": [
                    {
                        "line_number": 1,
                        "item_code": "ITM001",
                        "item_description": "Test Item",
                        "hsn_code": "8471",
                        "uom": "PCS",
                        "quantity": "10",
                        "unit_price": "1000.00",
                        "tax_rate": "0.18",
                        "tax_type": "IGST",
                        "discount_percent": "0",
                        "taxable_value": "10000.00",
                        "tax_amount": "1800.00",
                        "line_total": "11800.00",
                    }
                ],
                "taxes": {"cgst": "0", "sgst": "0", "igst": "1800.00", "cess": "0"},
                "totals": {"subtotal": "10000.00", "total_tax": "1800.00", "grand_total": "11800.00"},
                "expected_decision": "post" if i < 3 else "investigate",
                "defects": (
                    [{"type": "D01", "evidence": "", "details": {}}]
                    if i < 3
                    else [{"type": "D02", "evidence": "price variance", "details": {}}]
                ),
                "expected_actions": [],
            }
            with open(gt_dir / f"INV{i:06d}.json", "w") as f:
                json.dump(gt, f)

        results = run_oracle(gt_dir, output_dir)

        assert results["total"] == 5
        assert results["oracle_accuracy"] >= 0.8  # At least 80% match expected
        # decision_distribution has decision values as keys (post, investigate, etc.)
        assert len(results["decision_distribution"]) > 0
        assert sum(results["decision_distribution"].values()) == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
