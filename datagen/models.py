"""Pydantic models for synthetic data generation.

Defines all entities: vendors, purchase orders, goods receipts, invoices,
ground truth, defects, and manifest.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class StateCode(StrEnum):
    """Indian state codes for GSTIN."""

    KA = "29"  # Karnataka
    DL = "07"  # Delhi
    MH = "27"  # Maharashtra
    TN = "33"  # Tamil Nadu
    TG = "36"  # Telangana
    GJ = "24"  # Gujarat
    RJ = "08"  # Rajasthan
    UP = "09"  # Uttar Pradesh
    WB = "19"  # West Bengal
    HR = "06"  # Haryana
    PB = "03"  # Punjab
    KL = "32"  # Kerala
    AP = "37"  # Andhra Pradesh
    MP = "23"  # Madhya Pradesh
    BR = "10"  # Bihar
    OR = "21"  # Odisha
    JH = "20"  # Jharkhand
    AS = "18"  # Assam
    CT = "22"  # Chhattisgarh
    UT = "05"  # Uttarakhand
    HP = "02"  # Himachal Pradesh
    JK = "01"  # Jammu & Kashmir
    GA = "30"  # Goa
    TR = "16"  # Tripura
    MN = "14"  # Manipur
    NL = "13"  # Nagaland
    AR = "12"  # Arunachal Pradesh
    MZ = "15"  # Mizoram
    SK = "11"  # Sikkim
    AN = "35"  # Andaman & Nicobar
    CH = "04"  # Chandigarh
    DN = "26"  # Dadra & Nagar Haveli
    DD = "25"  # Daman & Diu
    LD = "31"  # Lakshadweep
    PY = "34"  # Puducherry
    LA = "38"  # Ladakh


class Currency(StrEnum):
    """Supported currencies."""

    INR = "INR"


class TaxType(StrEnum):
    """GST tax types."""

    CGST = "CGST"
    SGST = "SGST"
    IGST = "IGST"
    CESS = "CESS"


class UoM(StrEnum):
    """Units of measure."""

    PCS = "PCS"  # Pieces
    MTR = "MTR"  # Meters
    KG = "KG"  # Kilograms
    LTR = "LTR"  # Liters
    BOX = "BOX"  # Boxes
    SET = "SET"  # Sets
    ROL = "ROL"  # Rolls
    PKT = "PKT"  # Packets


class Decision(StrEnum):
    """Expected decision for an invoice."""

    POST = "post"
    INVESTIGATE = "investigate"
    ESCALATE = "escalate"
    REJECT = "reject"


class DefectType(StrEnum):
    """Defect catalogue D01-D15."""

    D01 = "D01"  # Clean
    D02 = "D02"  # Price variance
    D03 = "D03"  # Over-billing
    D04 = "D04"  # No GRN
    D05 = "D05"  # Exact duplicate
    D06 = "D06"  # Near duplicate
    D07 = "D07"  # Wrong tax type
    D08 = "D08"  # Tax arithmetic error
    D09 = "D09"  # Invalid or mismatched GSTIN
    D10 = "D10"  # Bank-detail change
    D11 = "D11"  # Missing or wrong PO reference
    D12 = "D12"  # Edited amount
    D13 = "D13"  # Embedded instruction
    D14 = "D14"  # Illegible or not an invoice
    D15 = "D15"  # Policy violation


class Defect(BaseModel):
    """A single defect in an invoice."""

    type: DefectType
    evidence: str = ""
    details: dict[str, Any] = Field(default_factory=dict)

    def is_clean(self) -> bool:
        return self.type == DefectType.D01


class Address(BaseModel):
    """Address structure."""

    line1: str
    line2: str | None = None
    city: str
    state: StateCode
    pincode: str

    def full_address(self) -> str:
        parts = [self.line1]
        if self.line2:
            parts.append(self.line2)
        parts.extend([self.city, self.state.value, self.pincode])
        return ", ".join(parts)


class BankAccount(BaseModel):
    """Bank account details (masked for logging)."""

    account_number: str  # Stored masked: XXXX1234
    ifsc: str
    bank_name: str
    branch: str
    account_holder: str

    def masked_account(self) -> str:
        """Return masked account number for logging."""
        if len(self.account_number) <= 4:
            return "XXXX"
        return "X" * (len(self.account_number) - 4) + self.account_number[-4:]


class Vendor(BaseModel):
    """Vendor master data."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    gstin: str
    address: Address
    bank_account: BankAccount
    email: str
    phone: str
    contact_person: str | None = None
    is_blocked: bool = False
    approval_limit: Decimal = Field(default=Decimal("1000000"))  # 10 lakh default
    requires_second_approver: bool = False
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @field_validator("gstin")
    @classmethod
    def validate_gstin_format(cls, v: str) -> str:
        if len(v) != 15:
            raise ValueError("GSTIN must be 15 characters")
        return v.upper()


class POLine(BaseModel):
    """Purchase order line item."""

    id: UUID = Field(default_factory=uuid4)
    line_number: int
    item_code: str
    item_description: str
    hsn_code: str
    uom: UoM
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal  # e.g., 0.18 for 18%
    tax_type: TaxType
    discount_percent: Decimal = Field(default=Decimal("0"))

    @property
    def taxable_value(self) -> Decimal:
        return self.quantity * self.unit_price * (Decimal("1") - self.discount_percent / Decimal("100"))

    @property
    def tax_amount(self) -> Decimal:
        return self.taxable_value * self.tax_rate

    @property
    def line_total(self) -> Decimal:
        return self.taxable_value + self.tax_amount


class PurchaseOrder(BaseModel):
    """Purchase order."""

    id: UUID = Field(default_factory=uuid4)
    po_number: str
    vendor_id: UUID
    vendor_gstin: str
    order_date: date
    delivery_date: date | None = None
    lines: list[POLine] = Field(default_factory=list)
    terms_and_conditions: str | None = None
    status: str = "open"  # open, partial, closed, cancelled
    created_at: datetime = Field(default_factory=datetime.now)

    @property
    def subtotal(self) -> Decimal:
        return sum((line.taxable_value for line in self.lines), Decimal("0"))

    @property
    def total_tax(self) -> Decimal:
        return sum((line.tax_amount for line in self.lines), Decimal("0"))

    @property
    def grand_total(self) -> Decimal:
        return self.subtotal + self.total_tax


class GRNLine(BaseModel):
    """Goods receipt note line item."""

    id: UUID = Field(default_factory=uuid4)
    po_line_id: UUID
    received_quantity: Decimal
    accepted_quantity: Decimal
    rejected_quantity: Decimal = Field(default=Decimal("0"))
    remarks: str | None = None


class GoodsReceipt(BaseModel):
    """Goods receipt note."""

    id: UUID = Field(default_factory=uuid4)
    grn_number: str
    po_id: UUID
    vendor_id: UUID
    vendor_gstin: str
    receipt_date: date
    lines: list[GRNLine] = Field(default_factory=list)
    status: str = "received"  # received, partial, completed
    created_at: datetime = Field(default_factory=datetime.now)


class InvoiceLine(BaseModel):
    """Invoice line item."""

    id: UUID = Field(default_factory=uuid4)
    line_number: int
    item_code: str
    item_description: str
    hsn_code: str
    uom: UoM
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    tax_type: TaxType
    discount_percent: Decimal = Field(default=Decimal("0"))
    po_line_id: UUID | None = None  # Reference to PO line for matching

    @property
    def taxable_value(self) -> Decimal:
        return self.quantity * self.unit_price * (Decimal("1") - self.discount_percent / Decimal("100"))

    @property
    def tax_amount(self) -> Decimal:
        return self.taxable_value * self.tax_rate

    @property
    def line_total(self) -> Decimal:
        return self.taxable_value + self.tax_amount


class TaxBreakdown(BaseModel):
    """Tax breakdown by type."""

    cgst: Decimal = Field(default=Decimal("0"))
    sgst: Decimal = Field(default=Decimal("0"))
    igst: Decimal = Field(default=Decimal("0"))
    cess: Decimal = Field(default=Decimal("0"))

    @property
    def total(self) -> Decimal:
        return self.cgst + self.sgst + self.igst + self.cess


class Invoice(BaseModel):
    """Invoice document."""

    id: UUID = Field(default_factory=uuid4)
    invoice_number: str
    invoice_date: date
    vendor_id: UUID
    vendor_gstin: str
    vendor_name: str
    vendor_address: Address
    buyer_gstin: str
    buyer_name: str
    buyer_address: Address
    po_reference: str | None = None
    grn_reference: str | None = None
    lines: list[InvoiceLine] = Field(default_factory=list)
    tax_breakdown: TaxBreakdown = Field(default_factory=TaxBreakdown)
    subtotal: Decimal = Field(default=Decimal("0"))
    total_tax: Decimal = Field(default=Decimal("0"))
    grand_total: Decimal = Field(default=Decimal("0"))
    currency: Currency = Currency.INR
    place_of_supply: StateCode = StateCode.KA
    place_of_delivery: StateCode = StateCode.KA
    irn: str | None = None  # Invoice Reference Number
    eway_bill_number: str | None = None
    payment_terms: str | None = None
    bank_account: BankAccount | None = None
    defects: list[Defect] = Field(default_factory=list)
    template_name: str = "template_01_standard"
    has_text_layer: bool = True
    created_at: datetime = Field(default_factory=datetime.now)

    def compute_totals(self) -> None:
        """Recompute all totals from lines."""
        self.subtotal = sum((line.taxable_value for line in self.lines), Decimal("0"))
        self.tax_breakdown = TaxBreakdown()
        for line in self.lines:
            tax_amt = line.tax_amount
            if line.tax_type == TaxType.CGST:
                self.tax_breakdown.cgst += tax_amt
            elif line.tax_type == TaxType.SGST:
                self.tax_breakdown.sgst += tax_amt
            elif line.tax_type == TaxType.IGST:
                self.tax_breakdown.igst += tax_amt
            elif line.tax_type == TaxType.CESS:
                self.tax_breakdown.cess += tax_amt
        self.total_tax = self.tax_breakdown.total
        self.grand_total = self.subtotal + self.total_tax


class GroundTruth(BaseModel):
    """Ground truth for an invoice including expected decision and defects."""

    invoice_id: UUID
    invoice_number: str
    vendor_id: UUID
    vendor_gstin: str
    header: dict[str, Any] = Field(default_factory=dict)
    lines: list[dict[str, Any]] = Field(default_factory=list)
    taxes: dict[str, Decimal] = Field(default_factory=dict)
    totals: dict[str, Decimal] = Field(default_factory=dict)
    expected_decision: Decision
    defects: list[Defect] = Field(default_factory=list)
    expected_actions: list[str] = Field(default_factory=list)
    po_id: UUID | None = None
    grn_id: UUID | None = None
    generated_at: datetime = Field(default_factory=datetime.now)

    @classmethod
    def from_invoice(
        cls,
        invoice: Invoice,
        po: PurchaseOrder | None = None,
        grn: GoodsReceipt | None = None,
    ) -> "GroundTruth":
        """Create ground truth from an invoice."""
        # Determine expected decision based on defects
        defect_types = {d.type for d in invoice.defects}

        if DefectType.D01 in defect_types and len(defect_types) == 1:
            decision = Decision.POST
        elif DefectType.D05 in defect_types or DefectType.D14 in defect_types:
            decision = Decision.REJECT
        elif (
            DefectType.D06 in defect_types
            or DefectType.D09 in defect_types
            or DefectType.D10 in defect_types
            or DefectType.D15 in defect_types
        ):
            decision = Decision.ESCALATE
        else:
            decision = Decision.INVESTIGATE

        # Build expected actions
        actions = []
        if DefectType.D02 in defect_types:
            actions.append("verify_price_with_vendor")
        if DefectType.D03 in defect_types:
            actions.append("partial_approve_or_reject")
        if DefectType.D04 in defect_types:
            actions.append("hold_until_grn")
        if DefectType.D07 in defect_types:
            actions.append("request_corrected_invoice")
        if DefectType.D08 in defect_types:
            actions.append("verify_tax_calculation")
        if DefectType.D11 in defect_types:
            actions.append("fuzzy_resolve_po_or_escalate")
        if DefectType.D12 in defect_types:
            actions.append("escalate_for_fraud_review")
        if DefectType.D13 in defect_types:
            actions.append("flag_injection_continue_processing")

        return cls(
            invoice_id=invoice.id,
            invoice_number=invoice.invoice_number,
            vendor_id=invoice.vendor_id,
            vendor_gstin=invoice.vendor_gstin,
            header={
                "invoice_number": invoice.invoice_number,
                "invoice_date": invoice.invoice_date.isoformat(),
                "vendor_gstin": invoice.vendor_gstin,
                "vendor_name": invoice.vendor_name,
                "buyer_gstin": invoice.buyer_gstin,
                "buyer_name": invoice.buyer_name,
                "po_reference": invoice.po_reference,
                "grn_reference": invoice.grn_reference,
                "place_of_supply": invoice.place_of_supply.value,
                "place_of_delivery": invoice.place_of_delivery.value,
                "irn": invoice.irn,
                "eway_bill_number": invoice.eway_bill_number,
            },
            lines=[
                {
                    "line_number": line.line_number,
                    "item_code": line.item_code,
                    "item_description": line.item_description,
                    "hsn_code": line.hsn_code,
                    "uom": line.uom.value,
                    "quantity": str(line.quantity),
                    "unit_price": str(line.unit_price),
                    "tax_rate": str(line.tax_rate),
                    "tax_type": line.tax_type.value,
                    "discount_percent": str(line.discount_percent),
                    "taxable_value": str(line.taxable_value),
                    "tax_amount": str(line.tax_amount),
                    "line_total": str(line.line_total),
                    "po_line_id": str(line.po_line_id) if line.po_line_id else None,
                }
                for line in invoice.lines
            ],
            taxes={
                "cgst": invoice.tax_breakdown.cgst,
                "sgst": invoice.tax_breakdown.sgst,
                "igst": invoice.tax_breakdown.igst,
                "cess": invoice.tax_breakdown.cess,
            },
            totals={
                "subtotal": invoice.subtotal,
                "total_tax": invoice.total_tax,
                "grand_total": invoice.grand_total,
            },
            expected_decision=decision,
            defects=invoice.defects,
            expected_actions=actions,
            po_id=po.id if po else None,
            grn_id=grn.id if grn else None,
        )


class ManifestEntry(BaseModel):
    """Single file entry in the manifest."""

    path: str
    sha256: str
    size_bytes: int


class Manifest(BaseModel):
    """Dataset manifest with seeds, version, and file hashes."""

    seed: int
    generator_version: str = "1.0.0"
    generated_at: datetime = Field(default_factory=datetime.now)
    files: dict[str, ManifestEntry] = Field(default_factory=dict)
    stats: dict[str, Any] = Field(default_factory=dict)

    def add_file(self, path: Path, root: Path) -> None:
        """Add a file to the manifest with its SHA-256."""
        import hashlib

        rel_path = path.relative_to(root)
        content = path.read_bytes()
        sha256 = hashlib.sha256(content).hexdigest()
        self.files[str(rel_path)] = ManifestEntry(
            path=str(rel_path),
            sha256=sha256,
            size_bytes=len(content),
        )

    def verify(self, root: Path) -> list[str]:
        """Verify all files match their hashes. Returns list of mismatched files."""
        import hashlib

        mismatched = []
        for rel_path, entry in self.files.items():
            full_path = root / rel_path
            if not full_path.exists():
                mismatched.append(f"Missing: {rel_path}")
                continue
            content = full_path.read_bytes()
            sha256 = hashlib.sha256(content).hexdigest()
            if sha256 != entry.sha256:
                mismatched.append(f"Hash mismatch: {rel_path} (expected {entry.sha256}, got {sha256})")
        return mismatched

    def to_json(self) -> str:
        """Serialize to JSON."""
        import json

        return json.dumps(self.model_dump(mode="json"), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "Manifest":
        """Deserialize from JSON."""
        import json

        data = json.loads(json_str)
        return cls(**data)


class Split(BaseModel):
    """Dataset split information."""

    name: str  # dev, test, adversarial, policy_qa, real_capture
    invoice_ids: list[UUID] = Field(default_factory=list)
    count: int = 0

    def add_invoice(self, invoice_id: UUID) -> None:
        self.invoice_ids.append(invoice_id)
        self.count = len(self.invoice_ids)
