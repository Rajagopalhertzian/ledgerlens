"""Matching models for entity resolution and 3-way matching."""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class MatchStatus(str, Enum):
    """Overall match status."""

    MATCHED = "matched"
    PARTIAL = "partial"
    MISMATCH = "mismatch"
    MISSING_PO = "missing_po"
    MISSING_GRN = "missing_grn"
    MISSING_INVOICE = "missing_invoice"


class LineMatchStatus(str, Enum):
    """Line-level match status."""

    MATCHED = "matched"
    PARTIAL = "partial"
    MISMATCH = "mismatch"
    QUANTITY_MISMATCH = "quantity_mismatch"
    PRICE_MISMATCH = "price_mismatch"
    TAX_MISMATCH = "tax_mismatch"
    MISSING_IN_GRN = "missing_in_grn"
    MISSING_IN_PO = "missing_in_po"
    MISSING_IN_INVOICE = "missing_in_invoice"
    EXTRA_IN_INVOICE = "extra_in_invoice"


@dataclass
class Discrepancy:
    """Represents a discrepancy in matching."""

    field: str
    invoice_value: str
    po_value: str | None = None
    grn_value: str | None = None
    difference: str | None = None
    tolerance: str | None = None
    severity: str = "medium"  # low, medium, high


@dataclass
class LineMatchResult:
    """Result of matching a single line item."""

    invoice_line_id: int | None
    invoice_line_number: int | None
    po_line_id: int | None = None
    po_line_number: int | None = None
    grn_line_id: int | None = None
    grn_line_number: int | None = None
    status: LineMatchStatus = LineMatchStatus.MISMATCH
    discrepancies: list[Discrepancy] = field(default_factory=list)

    # Matched quantities
    invoice_qty: Decimal | None = None
    po_qty: Decimal | None = None
    grn_qty: Decimal | None = None
    matched_qty: Decimal | None = None

    # Matched prices
    invoice_price: Decimal | None = None
    po_price: Decimal | None = None
    price_diff_pct: float | None = None

    # Tax
    invoice_tax_rate: Decimal | None = None
    po_tax_rate: Decimal | None = None
    tax_type_match: bool = True


@dataclass
class MatchResult:
    """Overall 3-way match result."""

    invoice_id: int
    invoice_number: str
    po_id: int | None = None
    po_number: str | None = None
    grn_id: int | None = None
    grn_number: str | None = None

    status: MatchStatus = MatchStatus.MISMATCH
    line_matches: list[LineMatchResult] = field(default_factory=list)
    discrepancies: list[Discrepancy] = field(default_factory=list)

    # Summary
    total_lines: int = 0
    matched_lines: int = 0
    partial_lines: int = 0
    mismatched_lines: int = 0
    missing_in_grn: int = 0
    missing_in_po: int = 0
    extra_in_invoice: int = 0

    # Totals comparison
    invoice_subtotal: Decimal | None = None
    po_subtotal: Decimal | None = None
    grn_subtotal: Decimal | None = None
    subtotal_diff_pct: float | None = None

    invoice_tax: Decimal | None = None
    po_tax: Decimal | None = None
    grn_tax: Decimal | None = None
    tax_diff_pct: float | None = None

    invoice_total: Decimal | None = None
    po_total: Decimal | None = None
    grn_total: Decimal | None = None
    total_diff_pct: float | None = None


@dataclass
class MatchingConfig:
    """Configuration for 3-way matching."""

    # Price tolerance percentage
    price_tolerance_pct: float = 2.0

    # Quantity tolerance (absolute)
    quantity_tolerance_abs: Decimal = Decimal("0.01")

    # UoM conversion factors (from_unit -> to_unit -> factor)
    uom_conversions: dict[str, dict[str, Decimal]] = field(default_factory=dict)

    # Per-HSN overrides
    hsn_overrides: dict[str, dict] = field(default_factory=dict)

    # Whether to require GRN for matching
    require_grn: bool = True

    # Whether to require PO for matching
    require_po: bool = True


@dataclass
class POCandidate:
    """PO candidate for entity resolution."""

    po_id: int
    po_number: str
    vendor_gstin: str
    vendor_name: str
    po_date: str
    grand_total: Decimal
    score: float
    match_reasons: list[str] = field(default_factory=list)


@dataclass
class VendorMatchResult:
    """Result of vendor resolution."""

    vendor_id: int | None
    vendor_gstin: str | None
    vendor_name: str | None
    match_type: str  # "exact_gstin", "fuzzy_name_address", "none"
    confidence: float
    candidates: list[dict] = field(default_factory=list)
