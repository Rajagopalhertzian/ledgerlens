"""Tests for evaluation harness metric functions."""

import json
from datetime import date
from decimal import Decimal

import pytest

from evals.harness import (
    bootstrap_ci,
    compare_baseline,
    expected_calibration_error,
    field_accuracy,
    match_line_items,
    normalize_currency,
    normalize_date,
    normalize_number,
    selective_prediction_curve,
    write_results,
)


class TestNormalizeNumber:
    """Tests for number normalization."""

    def test_plain_number(self):
        assert normalize_number("1234.56") == 1234.56

    def test_indian_grouping(self):
        assert normalize_number("12,34,567.00") == 1234567.00
        assert normalize_number("1,23,456.78") == 123456.78
        assert normalize_number("12,34,567") == 1234567.00

    def test_standard_grouping(self):
        assert normalize_number("1,234,567.89") == 1234567.89

    def test_currency_symbols(self):
        assert normalize_number("₹1,234.56") == 1234.56
        assert normalize_number("$1,234.56") == 1234.56
        assert normalize_number("INR 1,234.56") == 1234.56
        assert normalize_number("Rs. 1,234.56") == 1234.56

    def test_european_format(self):
        assert normalize_number("1.234,56") == 1234.56
        assert normalize_number("12.345,67") == 12345.67

    def test_parentheses_negative(self):
        assert normalize_number("(1,234.56)") == -1234.56

    def test_trailing_currency(self):
        assert normalize_number("1,234.56 INR") == 1234.56

    def test_lakh_crore(self):
        assert normalize_number("12.5 Lakh") == 1250000.0
        assert normalize_number("1.5 Cr") == 15000000.0

    def test_invalid_input(self):
        with pytest.raises(ValueError):
            normalize_number("")
        with pytest.raises(ValueError):
            normalize_number("abc")
        with pytest.raises(ValueError):
            normalize_number(None)  # type: ignore[arg-type]


class TestNormalizeDate:
    """Tests for date normalization."""

    def test_iso_format(self):
        assert normalize_date("2024-01-15") == date(2024, 1, 15)

    def test_dd_mm_yyyy(self):
        assert normalize_date("15/01/2024") == date(2024, 1, 15)
        assert normalize_date("15-01-2024") == date(2024, 1, 15)
        assert normalize_date("15.01.2024") == date(2024, 1, 15)

    def test_mm_dd_yyyy(self):
        assert normalize_date("01/15/2024") == date(2024, 1, 15)
        assert normalize_date("01-15-2024") == date(2024, 1, 15)

    def test_dd_mmm_yyyy(self):
        assert normalize_date("15-Jan-2024") == date(2024, 1, 15)
        assert normalize_date("15 January 2024") == date(2024, 1, 15)

    def test_with_time(self):
        assert normalize_date("2024-01-15T10:30:00") == date(2024, 1, 15)

    def test_invalid(self):
        with pytest.raises(ValueError):
            normalize_date("")
        with pytest.raises(ValueError):
            normalize_date("invalid")


class TestNormalizeCurrency:
    """Tests for currency normalization."""

    def test_returns_decimal(self):
        result = normalize_currency("1,234.56")
        assert isinstance(result, Decimal)
        assert result == Decimal("1234.56")

    def test_indian_format(self):
        result = normalize_currency("12,34,567.89")
        assert result == Decimal("1234567.89")

    def test_quantized(self):
        result = normalize_currency("1234.567")
        assert result == Decimal("1234.57")  # Rounded to 2 decimal places


class TestMatchLineItems:
    """Tests for line item matching."""

    def test_exact_match(self):
        pred = [{"item_description": "Widget A", "quantity": "10", "unit_price": "100"}]
        gt = [{"item_description": "Widget A", "quantity": "10", "unit_price": "100"}]
        result = match_line_items(pred, gt)
        assert result["precision"] == 1.0
        assert result["recall"] == 1.0
        assert result["f1"] == 1.0
        assert len(result["matches"]) == 1

    def test_partial_match(self):
        pred = [
            {"item_description": "Widget A", "quantity": "10", "unit_price": "100"},
            {"item_description": "Widget B", "quantity": "5", "unit_price": "200"},
        ]
        gt = [
            {"item_description": "Widget A", "quantity": "10", "unit_price": "100"},
        ]
        result = match_line_items(pred, gt)
        assert result["precision"] == 0.5
        assert result["recall"] == 1.0

    def test_no_match(self):
        pred = [{"item_description": "Widget A", "quantity": "10", "unit_price": "100"}]
        gt = [{"item_description": "Widget B", "quantity": "5", "unit_price": "200"}]
        result = match_line_items(pred, gt)
        assert result["precision"] == 0.0
        assert result["recall"] == 0.0

    def test_empty_lists(self):
        result = match_line_items([], [])
        assert result["precision"] == 1.0
        assert result["recall"] == 1.0
        assert result["f1"] == 1.0

    def test_pred_empty(self):
        result = match_line_items([], [{"item_description": "A", "quantity": "1", "unit_price": "100"}])
        assert result["precision"] == 0.0
        assert result["recall"] == 0.0

    def test_gt_empty(self):
        result = match_line_items([{"item_description": "A", "quantity": "1", "unit_price": "100"}], [])
        assert result["precision"] == 0.0
        assert result["recall"] == 0.0

    def test_numeric_tolerance(self):
        pred = [{"item_description": "A", "quantity": "10.00", "unit_price": "100.00"}]
        gt = [{"item_description": "A", "quantity": "10.01", "unit_price": "100.01"}]  # Small diff
        result = match_line_items(pred, gt)
        # Should still match with small numeric difference
        assert result["f1"] > 0.5


class TestBootstrapCI:
    """Tests for bootstrap confidence intervals."""

    def test_basic(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0] * 20  # 100 samples
        lower, upper = bootstrap_ci(data, n_bootstrap=100)
        assert lower < upper
        assert 2.5 < lower < 3.5
        assert 2.5 < upper < 3.5

    def test_empty(self):
        lower, upper = bootstrap_ci([])
        assert lower == 0.0
        assert upper == 0.0

    def test_different_statistics(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0] * 20
        lower_mean, upper_mean = bootstrap_ci(data, statistic="mean")
        lower_median, upper_median = bootstrap_ci(data, statistic="median")
        assert lower_mean < upper_mean
        assert lower_median < upper_median


class TestExpectedCalibrationError:
    """Tests for ECE."""

    def test_perfect_calibration(self):
        confidences = [0.9, 0.8, 0.7, 0.6, 0.5]
        accuracies = [1.0, 1.0, 1.0, 1.0, 1.0]  # All correct
        ece = expected_calibration_error(confidences, accuracies)
        # High confidence, all correct -> low ECE
        assert ece <= 0.3

    def test_poor_calibration(self):
        confidences = [0.9, 0.9, 0.9, 0.9, 0.9]
        accuracies = [0.0, 0.0, 0.0, 0.0, 0.0]  # All wrong despite high confidence
        ece = expected_calibration_error(confidences, accuracies)
        assert ece > 0.5

    def test_mismatched_lengths(self):
        with pytest.raises(ValueError):
            expected_calibration_error([0.9, 0.8], [1])

    def test_empty(self):
        ece = expected_calibration_error([], [])
        assert ece == 0.0


class TestSelectivePredictionCurve:
    """Tests for selective prediction curve."""

    def test_basic(self):
        confidences = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]
        accuracies = [1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        curve = selective_prediction_curve(confidences, accuracies, n_points=5)
        assert len(curve) == 5
        # Coverage should increase
        coverages = [c for c, _ in curve]
        assert all(coverages[i] <= coverages[i+1] for i in range(len(coverages)-1))

    def test_mismatched_lengths(self):
        with pytest.raises(ValueError):
            selective_prediction_curve([0.9], [1, 0])

    def test_empty(self):
        curve = selective_prediction_curve([], [])
        assert curve == []


class TestFieldAccuracy:
    """Tests for field-level accuracy."""

    def test_exact_match(self):
        pred = {"invoice_number": "INV001", "amount": "1000.00", "date": "2024-01-15"}
        gt = {"invoice_number": "INV001", "amount": "1000.00", "date": "2024-01-15"}
        acc = field_accuracy(pred, gt)
        assert all(v == 1.0 for v in acc.values())

    def test_numeric_tolerance(self):
        pred = {"amount": "1000.01"}
        gt = {"amount": "1000.00"}
        acc = field_accuracy(pred, gt)
        assert acc["amount"] == 1.0  # Within 0.01 tolerance

    def test_mismatch(self):
        pred = {"invoice_number": "INV001"}
        gt = {"invoice_number": "INV002"}
        acc = field_accuracy(pred, gt)
        assert acc["invoice_number"] == 0.0

    def test_missing_fields(self):
        pred = {"amount": "1000"}
        gt = {"amount": "1000", "date": "2024-01-15"}
        acc = field_accuracy(pred, gt, fields=["amount", "date"])
        assert acc["amount"] == 1.0
        assert acc["date"] == 0.0


class TestWriteResults:
    """Tests for results writer."""

    def test_write_json_and_md(self, tmp_path):
        results = {"metric1": 0.95, "metric2": {"sub": 0.8}}
        json_path, md_path = write_results(results, tmp_path, "test")

        assert json_path.exists()
        assert md_path.exists()

        # Check JSON
        with open(json_path) as f:
            loaded = json.load(f)
        assert loaded["metric1"] == 0.95

        # Check MD
        with open(md_path) as f:
            md = f.read()
        assert "Metric1" in md


class TestCompareBaseline:
    """Tests for baseline comparison."""

    def test_no_baseline(self, tmp_path):
        current = {"accuracy": 0.9}
        baseline_path = tmp_path / "nonexistent.json"
        report = compare_baseline(current, baseline_path)
        assert report["status"] == "no_baseline"

    def test_pass(self, tmp_path):
        current = {"accuracy": 0.95}
        baseline_path = tmp_path / "baseline.json"
        with open(baseline_path, "w") as f:
            json.dump({"accuracy": 0.94}, f)

        report = compare_baseline(current, baseline_path, tolerance=0.01)
        assert report["status"] == "pass"

    def test_regression(self, tmp_path):
        current = {"accuracy": 0.90}
        baseline_path = tmp_path / "baseline.json"
        with open(baseline_path, "w") as f:
            json.dump({"accuracy": 0.95}, f)

        report = compare_baseline(current, baseline_path, tolerance=0.01)
        assert report["status"] == "fail"
        assert len(report["regressions"]) == 1

    def test_improvement(self, tmp_path):
        current = {"accuracy": 0.98}
        baseline_path = tmp_path / "baseline.json"
        with open(baseline_path, "w") as f:
            json.dump({"accuracy": 0.95}, f)

        report = compare_baseline(current, baseline_path, tolerance=0.01)
        assert report["status"] == "pass"
        assert len(report["improvements"]) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
