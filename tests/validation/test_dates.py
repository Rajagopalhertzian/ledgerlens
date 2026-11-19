"""Tests for date validation (V7)."""

from datetime import date, timedelta
from hypothesis import given, strategies as st, settings

from ledgerlens.validation.dates import (
    parse_date,
    validate_invoice_date_plausibility,
    validate_invoice_not_before_po,
    validate_due_date,
    validate_grn_date,
    validate_all_dates,
)
from ledgerlens.db.models import Invoice, PurchaseOrder


class TestParseDate:
    """Tests for date parsing."""

    @given(st.dates(min_value=date(1900, 1, 1), max_value=date(2100, 12, 31)))
    def test_parse_iso_format(self, d: date):
        """ISO format YYYY-MM-DD should parse correctly."""
        result = parse_date(d.isoformat())
        assert result == d

    def test_parse_dd_mm_yyyy(self):
        """DD/MM/YYYY format should parse."""
        result = parse_date("31/12/2024")
        assert result == date(2024, 12, 31)

    def test_parse_dd_mm_yyyy_dash(self):
        """DD-MM-YYYY format should parse."""
        result = parse_date("31-12-2024")
        assert result == date(2024, 12, 31)

    def test_parse_dd_mm_yyyy_dot(self):
        """DD.MM.YYYY format should parse."""
        result = parse_date("31.12.2024")
        assert result == date(2024, 12, 31)

    def test_parse_invalid_returns_none(self):
        """Invalid date strings should return None."""
        assert parse_date("invalid") is None
        assert parse_date("32/13/2024") is None
        assert parse_date("") is None


class TestInvoiceDatePlausibility:
    """Tests for V7a: Invoice date plausibility."""

    def test_today_date_passes(self):
        """Today's date should pass."""
        today = date.today().isoformat()
        result = validate_invoice_date_plausibility(today)
        assert result.passed

    def test_yesterday_date_passes(self):
        """Yesterday's date should pass."""
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        result = validate_invoice_date_plausibility(yesterday)
        assert result.passed

    def test_future_date_fails(self):
        """Future date should fail."""
        future = (date.today() + timedelta(days=10)).isoformat()
        result = validate_invoice_date_plausibility(future)
        assert not result.passed
        assert "future" in result.message.lower()

    def test_very_old_date_fails(self):
        """Date older than 10 years should fail."""
        old_date = (date.today() - timedelta(days=3651)).isoformat()
        result = validate_invoice_date_plausibility(old_date)
        assert not result.passed
        assert "old" in result.message.lower()

    def test_10_years_old_passes(self):
        """Date exactly 10 years old should pass (boundary)."""
        old_date = (date.today() - timedelta(days=3650)).isoformat()
        result = validate_invoice_date_plausibility(old_date)
        assert result.passed

    @given(
        days_offset=st.integers(min_value=-3650, max_value=0)
    )
    @settings(max_examples=50)
    def test_past_dates_within_range_pass(self, days_offset: int):
        """Dates within 10 years in the past should pass."""
        test_date = (date.today() + timedelta(days=days_offset)).isoformat()
        result = validate_invoice_date_plausibility(test_date)
        assert result.passed


class TestInvoiceNotBeforePO:
    """Tests for V7b: Invoice date not before PO date."""

    def test_invoice_after_po_passes(self):
        """Invoice date after PO date should pass."""
        result = validate_invoice_not_before_po("2024-06-15", "2024-01-15")
        assert result.passed

    def test_invoice_same_as_po_passes(self):
        """Invoice date same as PO date should pass."""
        result = validate_invoice_not_before_po("2024-06-15", "2024-06-15")
        assert result.passed

    def test_invoice_before_po_fails(self):
        """Invoice date before PO date should fail."""
        result = validate_invoice_not_before_po("2024-01-15", "2024-06-15")
        assert not result.passed
        assert "before" in result.message.lower()

    def test_invalid_invoice_date_fails(self):
        """Invalid invoice date should fail."""
        result = validate_invoice_not_before_po("invalid", "2024-06-15")
        assert not result.passed

    def test_invalid_po_date_fails(self):
        """Invalid PO date should fail."""
        result = validate_invoice_not_before_po("2024-06-15", "invalid")
        assert not result.passed


class TestDueDate:
    """Tests for due date validation."""

    def test_due_after_invoice_passes(self):
        """Due date after invoice date should pass."""
        result = validate_due_date("2024-06-15", "2024-07-15")
        assert result.passed

    def test_due_same_as_invoice_passes(self):
        """Due date same as invoice date should pass."""
        result = validate_due_date("2024-06-15", "2024-06-15")
        assert result.passed

    def test_due_before_invoice_fails(self):
        """Due date before invoice date should fail."""
        result = validate_due_date("2024-06-15", "2024-06-10")
        assert not result.passed
        assert "before" in result.message.lower()

    def test_due_more_than_90_days_fails(self):
        """Due date more than 90 days after invoice should fail."""
        result = validate_due_date("2024-06-15", "2024-10-15")  # ~122 days
        assert not result.passed
        assert ">90 days" in result.message

    def test_due_exactly_90_days_passes(self):
        """Due date exactly 90 days after should pass (boundary)."""
        result = validate_due_date("2024-06-15", "2024-09-13")  # 90 days
        assert result.passed


class TestGRNDate:
    """Tests for GRN date validation."""

    def test_grn_after_po_passes(self):
        """GRN date after PO date should pass."""
        result = validate_grn_date("2024-06-15", "2024-01-15")
        assert result.passed

    def test_grn_before_po_fails(self):
        """GRN date before PO date should fail."""
        result = validate_grn_date("2024-01-15", "2024-06-15")
        assert not result.passed
        assert "before" in result.message.lower()


class TestValidateAllDates:
    """Tests for combined date validation."""

    def test_clean_invoice_passes_all(self):
        """Clean invoice with valid dates should pass all checks."""
        invoice = Invoice(
            invoice_date=date(2024, 6, 15),
            due_date=date(2024, 7, 15),
        )
        po = PurchaseOrder(po_date=date(2024, 1, 15))

        results = validate_all_dates(invoice, po)
        assert len(results) == 3  # plausibility, not before PO, due date
        assert all(r.passed for r in results)

    def test_future_invoice_date_fails_plausibility(self):
        """Future invoice date should fail plausibility check."""
        invoice = Invoice(
            invoice_date=date.today() + timedelta(days=10),
            due_date=date.today() + timedelta(days=40),
        )
        po = PurchaseOrder(po_date=date.today() - timedelta(days=10))

        results = validate_all_dates(invoice, po)
        assert any(not r.passed for r in results)

    def test_invoice_before_po_fails(self):
        """Invoice before PO should fail the PO date check."""
        invoice = Invoice(
            invoice_date=date(2024, 1, 15),
            due_date=date(2024, 2, 15),
        )
        po = PurchaseOrder(po_date=date(2024, 6, 15))

        results = validate_all_dates(invoice, po)
        assert any(not r.passed for r in results)

    def test_no_po_skips_po_check(self):
        """Without PO, PO date check should be skipped."""
        invoice = Invoice(
            invoice_date=date(2024, 6, 15),
            due_date=date(2024, 7, 15),
        )

        results = validate_all_dates(invoice, None)
        assert len(results) == 2  # plausibility and due date only
        assert all(r.passed for r in results)


# Property-based tests for date parsing
class TestDateParsingProperties:
    """Property-based tests for date parsing."""

    @given(st.dates(min_value=date(2000, 1, 1), max_value=date(2050, 12, 31)))
    def test_iso_format_roundtrip(self, d: date):
        """ISO format should roundtrip correctly."""
        parsed = parse_date(d.isoformat())
        assert parsed == d

    @given(
        day=st.integers(min_value=1, max_value=28),
        month=st.integers(min_value=1, max_value=12),
        year=st.integers(min_value=2000, max_value=2050),
    )
    def test_dd_mm_yyyy_roundtrip(self, day: int, month: int, year: int):
        """DD/MM/YYYY should parse correctly."""
        date_str = f"{day:02d}/{month:02d}/{year:04d}"
        parsed = parse_date(date_str)
        assert parsed == date(year, month, day)
