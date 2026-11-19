"""Pydantic models for extraction results."""

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ExtractionSource(StrEnum):
    """Source of the extracted value."""

    OCR = "ocr"
    VLM = "vlm"
    TEXT_PARSER = "text_parser"
    FUSED = "fused"


class FieldType(StrEnum):
    """Type of extracted field for metric grouping."""

    VENDOR_NAME = "vendor_name"
    VENDOR_GSTIN = "vendor_gstin"
    INVOICE_NUMBER = "invoice_number"
    INVOICE_DATE = "invoice_date"
    BUYER_GSTIN = "buyer_gstin"
    BUYER_NAME = "buyer_name"
    PO_REFERENCE = "po_reference"
    GRN_REFERENCE = "grn_reference"
    SUBTOTAL = "subtotal"
    TOTAL_TAX = "total_tax"
    GRAND_TOTAL = "grand_total"
    CURRENCY = "currency"
    PLACE_OF_SUPPLY = "place_of_supply"
    PLACE_OF_DELIVERY = "place_of_delivery"
    IRN = "irn"
    EWAY_BILL_NUMBER = "eway_bill_number"
    PAYMENT_TERMS = "payment_terms"
    ITEM_DESCRIPTION = "item_description"
    HSN_CODE = "hsn_code"
    QUANTITY = "quantity"
    UNIT_PRICE = "unit_price"
    TAX_RATE = "tax_rate"
    TAX_TYPE = "tax_type"
    DISCOUNT_PERCENT = "discount_percent"
    TAXABLE_VALUE = "taxable_value"
    TAX_AMOUNT = "tax_amount"
    LINE_TOTAL = "line_total"
    UOM = "uom"
    ITEM_CODE = "item_code"
    BANK_ACCOUNT = "bank_account"
    IFSC = "ifsc"


class BoundingBox(BaseModel):
    """Bounding box in image coordinates (pixels)."""

    x: int
    y: int
    width: int
    height: int

    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    def overlaps(self, other: "BoundingBox", threshold: float = 0.1) -> bool:
        """Check if boxes overlap with given IoU threshold."""
        x1 = max(self.x, other.x)
        y1 = max(self.y, other.y)
        x2 = min(self.x + self.width, other.x + other.width)
        y2 = min(self.y + self.height, other.y + other.height)

        if x2 <= x1 or y2 <= y1:
            return False

        intersection = (x2 - x1) * (y2 - y1)
        area1 = self.width * self.height
        area2 = other.width * other.height
        union = area1 + area2 - intersection
        return intersection / union >= threshold


class OCRToken(BaseModel):
    """Single token from OCR with position and confidence."""

    text: str
    bbox: BoundingBox
    confidence: float = Field(ge=0.0, le=1.0)
    block_num: int | None = None
    line_num: int | None = None
    word_num: int | None = None

    def normalized_text(self) -> str:
        """Return normalized text for comparison."""
        return self.text.strip().lower()


class EvidenceSpan(BaseModel):
    """Evidence for an extracted value - OCR tokens or text spans."""

    source: ExtractionSource
    token_indices: list[int] = Field(default_factory=list)  # Indices into OCR token list
    text_spans: list[tuple[int, int]] = Field(default_factory=list)  # (start, end) in full text
    bboxes: list[BoundingBox] = Field(default_factory=list)
    raw_text: str = ""

    def is_grounded(self) -> bool:
        """Check if evidence is grounded in OCR tokens."""
        return self.source in (ExtractionSource.OCR, ExtractionSource.FUSED) and len(self.token_indices) > 0


class ExtractedField(BaseModel):
    """A single extracted field with confidence and evidence."""

    field_type: FieldType
    value: str  # Raw extracted string
    normalized_value: str | None = None  # After normalization (numbers, dates, etc.)
    confidence: float = Field(ge=0.0, le=1.0)  # Raw model confidence
    calibrated_confidence: float | None = None  # After calibration
    evidence: EvidenceSpan
    source: ExtractionSource
    grounded: bool = False  # Whether value was found in OCR tokens
    warnings: list[str] = Field(default_factory=list)

    def get_typed_value(self) -> Any:
        """Get value converted to appropriate Python type."""
        if self.normalized_value is None:
            return self.value

        # Try numeric
        try:
            if "." in self.normalized_value:
                return float(self.normalized_value)
            return int(self.normalized_value)
        except ValueError:
            pass

        # Try date
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
            try:
                if fmt == "%Y-%m-%d":
                    return date.fromisoformat(self.normalized_value)
                return datetime.strptime(self.normalized_value, fmt).date()
            except ValueError:
                continue

        return self.normalized_value


class LineItem(BaseModel):
    """Extracted line item."""

    id: UUID = Field(default_factory=uuid4)
    line_number: int | None = None
    item_code: ExtractedField | None = None
    item_description: ExtractedField | None = None
    hsn_code: ExtractedField | None = None
    uom: ExtractedField | None = None
    quantity: ExtractedField | None = None
    unit_price: ExtractedField | None = None
    tax_rate: ExtractedField | None = None
    tax_type: ExtractedField | None = None
    discount_percent: ExtractedField | None = None
    taxable_value: ExtractedField | None = None
    tax_amount: ExtractedField | None = None
    line_total: ExtractedField | None = None
    po_line_id: UUID | None = None  # For matching

    def get_all_fields(self) -> list[ExtractedField]:
        """Get all non-None fields as a list."""
        fields = []
        for attr in [
            "item_code",
            "item_description",
            "hsn_code",
            "uom",
            "quantity",
            "unit_price",
            "tax_rate",
            "tax_type",
            "discount_percent",
            "taxable_value",
            "tax_amount",
            "line_total",
        ]:
            val = getattr(self, attr)
            if val is not None:
                fields.append(val)
        return fields


class ValidationResult(BaseModel):
    """Result of a deterministic validation check."""

    validator_name: str
    passed: bool
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class CalibratedConfidence(BaseModel):
    """Calibrated confidence with components."""

    raw_confidence: float = Field(ge=0.0, le=1.0)
    ocr_confidence: float | None = None
    vlm_confidence: float | None = None
    grounded: bool = False
    validator_results: list[ValidationResult] = Field(default_factory=list)
    calibrated: float = Field(ge=0.0, le=1.0)

    @property
    def validator_pass_rate(self) -> float:
        if not self.validator_results:
            return 1.0
        return sum(1 for v in self.validator_results if v.passed) / len(self.validator_results)


class ExtractionResult(BaseModel):
    """Complete extraction result for an invoice."""

    id: UUID = Field(default_factory=uuid4)
    document_path: str
    config_name: str  # E0, E1, E2, E3, E4, E5

    # Header fields
    vendor_name: ExtractedField | None = None
    vendor_gstin: ExtractedField | None = None
    invoice_number: ExtractedField | None = None
    invoice_date: ExtractedField | None = None
    buyer_gstin: ExtractedField | None = None
    buyer_name: ExtractedField | None = None
    po_reference: ExtractedField | None = None
    grn_reference: ExtractedField | None = None
    subtotal: ExtractedField | None = None
    total_tax: ExtractedField | None = None
    grand_total: ExtractedField | None = None
    currency: ExtractedField | None = None
    place_of_supply: ExtractedField | None = None
    place_of_delivery: ExtractedField | None = None
    irn: ExtractedField | None = None
    eway_bill_number: ExtractedField | None = None
    payment_terms: ExtractedField | None = None
    bank_account: ExtractedField | None = None
    ifsc: ExtractedField | None = None

    # Line items
    line_items: list[LineItem] = Field(default_factory=list)

    # OCR tokens (for grounding)
    ocr_tokens: list[OCRToken] = Field(default_factory=list)

    # Full extracted text
    full_text: str = ""

    # Validations
    validations: list[ValidationResult] = Field(default_factory=list)

    # Calibrated confidences per field
    calibrated_confidences: dict[FieldType, CalibratedConfidence] = Field(default_factory=dict)

    # Metadata
    extraction_time_ms: float = 0.0
    cost_usd: float = 0.0
    warnings: list[str] = Field(default_factory=list)

    def get_header_fields(self) -> dict[FieldType, ExtractedField]:
        """Get all header fields as a dict."""
        fields = {}
        for attr_name, field_type in [
            ("vendor_name", FieldType.VENDOR_NAME),
            ("vendor_gstin", FieldType.VENDOR_GSTIN),
            ("invoice_number", FieldType.INVOICE_NUMBER),
            ("invoice_date", FieldType.INVOICE_DATE),
            ("buyer_gstin", FieldType.BUYER_GSTIN),
            ("buyer_name", FieldType.BUYER_NAME),
            ("po_reference", FieldType.PO_REFERENCE),
            ("grn_reference", FieldType.GRN_REFERENCE),
            ("subtotal", FieldType.SUBTOTAL),
            ("total_tax", FieldType.TOTAL_TAX),
            ("grand_total", FieldType.GRAND_TOTAL),
            ("currency", FieldType.CURRENCY),
            ("place_of_supply", FieldType.PLACE_OF_SUPPLY),
            ("place_of_delivery", FieldType.PLACE_OF_DELIVERY),
            ("irn", FieldType.IRN),
            ("eway_bill_number", FieldType.EWAY_BILL_NUMBER),
            ("payment_terms", FieldType.PAYMENT_TERMS),
            ("bank_account", FieldType.BANK_ACCOUNT),
            ("ifsc", FieldType.IFSC),
        ]:
            val = getattr(self, attr_name)
            if val is not None:
                fields[field_type] = val
        return fields

    def get_all_fields(self) -> list[ExtractedField]:
        """Get all extracted fields (header + line items)."""
        fields = list(self.get_header_fields().values())
        for item in self.line_items:
            fields.extend(item.get_all_fields())
        return fields
