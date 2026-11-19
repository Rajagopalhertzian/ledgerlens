"""SQLAlchemy models for ERP database schema.

Tables:
- vendors: vendor master data
- purchase_orders + po_lines: POs with HSN, UoM, tax rates
- goods_receipts + grn_lines: GRNs with partial deliveries
- invoices + invoice_lines: invoices with defects
- approvals: approval workflow state
- posting_ledger: idempotency keys for ERP posts
- audit_log: append-only, hash-chained audit trail
- outbox: drafted emails and tickets
"""

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class TaxType(PyEnum):
    """GST tax type."""

    CGST = "CGST"
    SGST = "SGST"
    IGST = "IGST"
    CESS = "CESS"


class InvoiceStatus(PyEnum):
    """Invoice processing status."""

    DRAFT = "draft"
    VALIDATED = "validated"
    MATCHED = "matched"
    PARTIAL = "partial"
    MISMATCH = "mismatch"
    NEEDS_APPROVAL = "needs_approval"
    APPROVED = "approved"
    POSTED = "posted"
    REJECTED = "rejected"


class ApprovalStatus(PyEnum):
    """Approval workflow status."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"


class POStatus(PyEnum):
    """Purchase order status."""

    OPEN = "open"
    PARTIAL = "partial"
    COMPLETE = "complete"
    CLOSED = "closed"


class GRNStatus(PyEnum):
    """Goods receipt status."""

    OPEN = "open"
    PARTIAL = "partial"
    COMPLETE = "complete"


class Vendor(Base):
    """Vendor master data."""

    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gstin: Mapped[str] = mapped_column(String(15), unique=True, nullable=False, index=True)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trade_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    pincode: Mapped[str] = mapped_column(String(6), nullable=False)
    country: Mapped[str] = mapped_column(String(2), default="IN", nullable=False)
    bank_account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bank_account_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bank_ifsc: Mapped[str | None] = mapped_column(String(11), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contact_person: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pan: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(back_populates="vendor")
    goods_receipts: Mapped[list["GoodsReceipt"]] = relationship(back_populates="vendor")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="vendor")

    __table_args__ = (
        Index("ix_vendors_gstin_active", "gstin", "is_active"),
        CheckConstraint("length(gstin) = 15", name="ck_vendors_gstin_length"),
    )

    def __repr__(self) -> str:
        return f"<Vendor(id={self.id}, gstin={self.gstin}, name={self.legal_name})>"


class PurchaseOrder(Base):
    """Purchase order header."""

    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    po_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), nullable=False)
    po_date: Mapped[date] = mapped_column(Date, nullable=False)
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    buyer_gstin: Mapped[str] = mapped_column(String(15), nullable=False)
    buyer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    buyer_address: Mapped[str] = mapped_column(Text, nullable=False)
    buyer_state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    place_of_supply: Mapped[str] = mapped_column(String(2), nullable=False)
    status: Mapped[POStatus] = mapped_column(Enum(POStatus), default=POStatus.OPEN, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0, nullable=False)
    total_tax: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0, nullable=False)
    grand_total: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    vendor: Mapped["Vendor"] = relationship(back_populates="purchase_orders")
    lines: Mapped[list["POLine"]] = relationship(back_populates="po", cascade="all, delete-orphan")
    goods_receipts: Mapped[list["GoodsReceipt"]] = relationship(back_populates="po")

    __table_args__ = (
        Index("ix_po_vendor_date", "vendor_id", "po_date"),
        CheckConstraint("grand_total >= 0", name="ck_po_grand_total_positive"),
    )

    def __repr__(self) -> str:
        return f"<PurchaseOrder(id={self.id}, po_number={self.po_number})>"


class POLine(Base):
    """Purchase order line item."""

    __tablename__ = "po_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    item_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    item_description: Mapped[str] = mapped_column(Text, nullable=False)
    hsn_code: Mapped[str] = mapped_column(String(8), nullable=False)
    uom: Mapped[str] = mapped_column(String(20), nullable=False)  # Unit of measure
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    tax_type: Mapped[TaxType] = mapped_column(Enum(TaxType), nullable=False)
    taxable_value: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    po: Mapped["PurchaseOrder"] = relationship(back_populates="lines")

    __table_args__ = (
        UniqueConstraint("po_id", "line_number", name="uq_po_line_number"),
        CheckConstraint("quantity > 0", name="ck_po_line_qty_positive"),
        CheckConstraint("unit_price >= 0", name="ck_po_line_price_nonneg"),
        CheckConstraint("tax_rate >= 0", name="ck_po_line_tax_rate_nonneg"),
    )

    def __repr__(self) -> str:
        return f"<POLine(id={self.id}, po_id={self.po_id}, line={self.line_number})>"


class GoodsReceipt(Base):
    """Goods receipt note header."""

    __tablename__ = "goods_receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    grn_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), nullable=False)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), nullable=False)
    grn_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[GRNStatus] = mapped_column(Enum(GRNStatus), default=GRNStatus.OPEN, nullable=False)
    received_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    po: Mapped["PurchaseOrder"] = relationship(back_populates="goods_receipts")
    vendor: Mapped["Vendor"] = relationship(back_populates="goods_receipts")
    lines: Mapped[list["GRNLine"]] = relationship(back_populates="grn", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_grn_po_date", "po_id", "grn_date"),
        Index("ix_grn_vendor_date", "vendor_id", "grn_date"),
    )

    def __repr__(self) -> str:
        return f"<GoodsReceipt(id={self.id}, grn_number={self.grn_number})>"


class GRNLine(Base):
    """Goods receipt line item."""

    __tablename__ = "grn_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    grn_id: Mapped[int] = mapped_column(ForeignKey("goods_receipts.id", ondelete="CASCADE"), nullable=False)
    po_line_id: Mapped[int] = mapped_column(ForeignKey("po_lines.id"), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(15, 3), nullable=False)
    quantity_accepted: Mapped[Decimal] = mapped_column(Numeric(15, 3), nullable=False)
    quantity_rejected: Mapped[Decimal] = mapped_column(Numeric(15, 3), default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    grn: Mapped["GoodsReceipt"] = relationship(back_populates="lines")
    po_line: Mapped["POLine"] = relationship()

    __table_args__ = (
        UniqueConstraint("grn_id", "line_number", name="uq_grn_line_number"),
        CheckConstraint("quantity_received >= 0", name="ck_grn_line_qty_recv_nonneg"),
        CheckConstraint("quantity_accepted >= 0", name="ck_grn_line_qty_acc_nonneg"),
        CheckConstraint("quantity_rejected >= 0", name="ck_grn_line_qty_rej_nonneg"),
    )

    def __repr__(self) -> str:
        return f"<GRNLine(id={self.id}, grn_id={self.grn_id}, line={self.line_number})>"


class Invoice(Base):
    """Invoice header."""

    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    buyer_gstin: Mapped[str] = mapped_column(String(15), nullable=False)
    buyer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    buyer_address: Mapped[str] = mapped_column(Text, nullable=False)
    buyer_state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    place_of_supply: Mapped[str] = mapped_column(String(2), nullable=False)
    place_of_delivery: Mapped[str] = mapped_column(String(2), nullable=True)
    po_reference: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    grn_reference: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    irn: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    eway_bill_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0, nullable=False)
    total_tax: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0, nullable=False)
    grand_total: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0, nullable=False)
    cgst_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0, nullable=False)
    sgst_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0, nullable=False)
    igst_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0, nullable=False)
    cess_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0, nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(Enum(InvoiceStatus), default=InvoiceStatus.DRAFT, nullable=False)
    approval_status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False
    )
    payment_terms: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bank_account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bank_account_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bank_ifsc: Mapped[str | None] = mapped_column(String(11), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    defect_flags: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    erp_document_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    vendor: Mapped["Vendor"] = relationship(back_populates="invoices")
    lines: Mapped[list["InvoiceLine"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    approvals: Mapped[list["Approval"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("vendor_id", "invoice_number", name="uq_vendor_invoice_number"),
        Index("ix_invoice_vendor_date", "vendor_id", "invoice_date"),
        Index("ix_invoice_po_ref", "po_reference"),
        Index("ix_invoice_grn_ref", "grn_reference"),
        Index("ix_invoice_status_date", "status", "invoice_date"),
        CheckConstraint("grand_total >= 0", name="ck_invoice_grand_total_positive"),
    )

    def __repr__(self) -> str:
        return f"<Invoice(id={self.id}, number={self.invoice_number}, status={self.status})>"


class InvoiceLine(Base):
    """Invoice line item."""

    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    item_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    item_description: Mapped[str] = mapped_column(Text, nullable=False)
    hsn_code: Mapped[str] = mapped_column(String(8), nullable=False)
    uom: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    tax_type: Mapped[TaxType] = mapped_column(Enum(TaxType), nullable=False)
    taxable_value: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    cgst_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0, nullable=False)
    sgst_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0, nullable=False)
    igst_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0, nullable=False)
    cess_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0, nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    po_line_id: Mapped[int | None] = mapped_column(ForeignKey("po_lines.id"), nullable=True)
    grn_line_id: Mapped[int | None] = mapped_column(ForeignKey("grn_lines.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    invoice: Mapped["Invoice"] = relationship(back_populates="lines")
    po_line: Mapped[Optional["POLine"]] = relationship()
    grn_line: Mapped[Optional["GRNLine"]] = relationship()

    __table_args__ = (
        UniqueConstraint("invoice_id", "line_number", name="uq_invoice_line_number"),
        CheckConstraint("quantity > 0", name="ck_inv_line_qty_positive"),
        CheckConstraint("unit_price >= 0", name="ck_inv_line_price_nonneg"),
        CheckConstraint("tax_rate >= 0", name="ck_inv_line_tax_rate_nonneg"),
    )

    def __repr__(self) -> str:
        return f"<InvoiceLine(id={self.id}, invoice_id={self.invoice_id}, line={self.line_number})>"


class Approval(Base):
    """Approval workflow state."""

    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    approver_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approver_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[ApprovalStatus] = mapped_column(Enum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_token: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    invoice: Mapped["Invoice"] = relationship(back_populates="approvals")

    __table_args__ = (
        UniqueConstraint("invoice_id", "level", name="uq_approval_invoice_level"),
        Index("ix_approval_token", "approval_token"),
        Index("ix_approval_idempotency", "idempotency_key"),
    )

    def __repr__(self) -> str:
        return f"<Approval(id={self.id}, invoice_id={self.invoice_id}, status={self.status})>"


class PostingLedger(Base):
    """Idempotency keys for ERP posts."""

    __tablename__ = "posting_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # post_invoice, place_payment_hold
    erp_document_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    response_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # success, failed, pending
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_posting_invoice_action", "invoice_id", "action"),)

    def __repr__(self) -> str:
        return f"<PostingLedger(id={self.id}, key={self.idempotency_key[:16]}..., status={self.status})>"


class AuditLog(Base):
    """Append-only, hash-chained audit trail."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    actor: Mapped[str | None] = mapped_column(String(100), nullable=True)
    action: Mapped[str | None] = mapped_column(String(50), nullable=True)
    success: Mapped[bool] = mapped_column(default=True, nullable=False)
    before_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_created", "created_at"),
        Index("ix_audit_actor", "actor"),
    )

    @staticmethod
    def compute_hash(
        previous_hash: str | None, event_type: str, entity_type: str, entity_id: int, payload: dict
    ) -> str:
        """Compute hash for audit log entry."""
        data = {
            "previous_hash": previous_hash,
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "payload": payload,
            "timestamp": datetime.utcnow().isoformat(),
        }
        serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode()).hexdigest()

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, event={self.event_type}, entity={self.entity_type}:{self.entity_id})>"


class Outbox(Base):
    """Drafted emails and tickets for async processing."""

    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_type: Mapped[str] = mapped_column(String(50), nullable=False)  # email, ticket, webhook
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending, sent, failed
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_outbox_status_scheduled", "status", "scheduled_at"),)

    def __repr__(self) -> str:
        return f"<Outbox(id={self.id}, type={self.message_type}, status={self.status})>"
