"""Initial migration - create all tables.

Revision ID: 001_initial
Revises:
Create Date: 2024-01-15 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create enum types
    tax_type = sa.Enum("CGST", "SGST", "IGST", "CESS", name="tax_type")
    tax_type.create(op.get_bind(), checkfirst=True)

    invoice_status = sa.Enum(
        "draft",
        "validated",
        "matched",
        "partial",
        "mismatch",
        "needs_approval",
        "approved",
        "posted",
        "rejected",
        name="invoice_status",
    )
    invoice_status.create(op.get_bind(), checkfirst=True)

    approval_status = sa.Enum("pending", "approved", "rejected", "escalated", name="approval_status")
    approval_status.create(op.get_bind(), checkfirst=True)

    po_status = sa.Enum("open", "partial", "complete", "closed", name="po_status")
    po_status.create(op.get_bind(), checkfirst=True)

    grn_status = sa.Enum("open", "partial", "complete", name="grn_status")
    grn_status.create(op.get_bind(), checkfirst=True)

    # vendors table
    op.create_table(
        "vendors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("gstin", sa.String(length=15), nullable=False),
        sa.Column("legal_name", sa.String(length=255), nullable=False),
        sa.Column("trade_name", sa.String(length=255), nullable=True),
        sa.Column("address_line1", sa.String(length=255), nullable=False),
        sa.Column("address_line2", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("state_code", sa.String(length=2), nullable=False),
        sa.Column("pincode", sa.String(length=6), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False, server_default="IN"),
        sa.Column("bank_account_name", sa.String(length=255), nullable=True),
        sa.Column("bank_account_number", sa.String(length=50), nullable=True),
        sa.Column("bank_ifsc", sa.String(length=11), nullable=True),
        sa.Column("bank_name", sa.String(length=100), nullable=True),
        sa.Column("contact_person", sa.String(length=100), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=20), nullable=True),
        sa.Column("pan", sa.String(length=10), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gstin"),
        sa.CheckConstraint("length(gstin) = 15", name="ck_vendors_gstin_length"),
    )
    op.create_index("ix_vendors_gstin_active", "vendors", ["gstin", "is_active"], unique=False)

    # purchase_orders table
    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("po_number", sa.String(length=50), nullable=False),
        sa.Column("vendor_id", sa.Integer(), nullable=False),
        sa.Column("po_date", sa.Date(), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=True),
        sa.Column("buyer_gstin", sa.String(length=15), nullable=False),
        sa.Column("buyer_name", sa.String(length=255), nullable=False),
        sa.Column("buyer_address", sa.Text(), nullable=False),
        sa.Column("buyer_state_code", sa.String(length=2), nullable=False),
        sa.Column("place_of_supply", sa.String(length=2), nullable=False),
        sa.Column(
            "status",
            sa.Enum("open", "partial", "complete", "closed", name="po_status"),
            nullable=False,
            server_default="open",
        ),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
        sa.Column("subtotal", sa.Numeric(precision=15, scale=2), nullable=False, server_default="0"),
        sa.Column("total_tax", sa.Numeric(precision=15, scale=2), nullable=False, server_default="0"),
        sa.Column("grand_total", sa.Numeric(precision=15, scale=2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("po_number"),
        sa.CheckConstraint("grand_total >= 0", name="ck_po_grand_total_positive"),
    )
    op.create_index("ix_po_vendor_date", "purchase_orders", ["vendor_id", "po_date"], unique=False)

    # po_lines table
    op.create_table(
        "po_lines",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("po_id", sa.Integer(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("item_code", sa.String(length=50), nullable=True),
        sa.Column("item_description", sa.Text(), nullable=False),
        sa.Column("hsn_code", sa.String(length=8), nullable=False),
        sa.Column("uom", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=15, scale=3), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("discount_percent", sa.Numeric(precision=5, scale=2), nullable=False, server_default="0"),
        sa.Column("tax_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("tax_type", sa.Enum("CGST", "SGST", "IGST", "CESS", name="tax_type"), nullable=False),
        sa.Column("taxable_value", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["po_id"], ["purchase_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("po_id", "line_number", name="uq_po_line_number"),
        sa.CheckConstraint("quantity > 0", name="ck_po_line_qty_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_po_line_price_nonneg"),
        sa.CheckConstraint("tax_rate >= 0", name="ck_po_line_tax_rate_nonneg"),
    )

    # goods_receipts table
    op.create_table(
        "goods_receipts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("grn_number", sa.String(length=50), nullable=False),
        sa.Column("po_id", sa.Integer(), nullable=False),
        sa.Column("vendor_id", sa.Integer(), nullable=False),
        sa.Column("grn_date", sa.Date(), nullable=False),
        sa.Column(
            "status", sa.Enum("open", "partial", "complete", name="grn_status"), nullable=False, server_default="open"
        ),
        sa.Column("received_by", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["po_id"], ["purchase_orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("grn_number"),
    )
    op.create_index("ix_grn_po_date", "goods_receipts", ["po_id", "grn_date"], unique=False)
    op.create_index("ix_grn_vendor_date", "goods_receipts", ["vendor_id", "grn_date"], unique=False)

    # grn_lines table
    op.create_table(
        "grn_lines",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("grn_id", sa.Integer(), nullable=False),
        sa.Column("po_line_id", sa.Integer(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("quantity_received", sa.Numeric(precision=15, scale=3), nullable=False),
        sa.Column("quantity_accepted", sa.Numeric(precision=15, scale=3), nullable=False),
        sa.Column("quantity_rejected", sa.Numeric(precision=15, scale=3), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["grn_id"], ["goods_receipts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["po_line_id"], ["po_lines.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("grn_id", "line_number", name="uq_grn_line_number"),
        sa.CheckConstraint("quantity_received >= 0", name="ck_grn_line_qty_recv_nonneg"),
        sa.CheckConstraint("quantity_accepted >= 0", name="ck_grn_line_qty_acc_nonneg"),
        sa.CheckConstraint("quantity_rejected >= 0", name="ck_grn_line_qty_rej_nonneg"),
    )

    # invoices table
    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("invoice_number", sa.String(length=50), nullable=False),
        sa.Column("vendor_id", sa.Integer(), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("buyer_gstin", sa.String(length=15), nullable=False),
        sa.Column("buyer_name", sa.String(length=255), nullable=False),
        sa.Column("buyer_address", sa.Text(), nullable=False),
        sa.Column("buyer_state_code", sa.String(length=2), nullable=False),
        sa.Column("place_of_supply", sa.String(length=2), nullable=False),
        sa.Column("place_of_delivery", sa.String(length=2), nullable=True),
        sa.Column("po_reference", sa.String(length=50), nullable=True),
        sa.Column("grn_reference", sa.String(length=50), nullable=True),
        sa.Column("irn", sa.String(length=64), nullable=True),
        sa.Column("eway_bill_number", sa.String(length=20), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
        sa.Column("subtotal", sa.Numeric(precision=15, scale=2), nullable=False, server_default="0"),
        sa.Column("total_tax", sa.Numeric(precision=15, scale=2), nullable=False, server_default="0"),
        sa.Column("grand_total", sa.Numeric(precision=15, scale=2), nullable=False, server_default="0"),
        sa.Column("cgst_amount", sa.Numeric(precision=15, scale=2), nullable=False, server_default="0"),
        sa.Column("sgst_amount", sa.Numeric(precision=15, scale=2), nullable=False, server_default="0"),
        sa.Column("igst_amount", sa.Numeric(precision=15, scale=2), nullable=False, server_default="0"),
        sa.Column("cess_amount", sa.Numeric(precision=15, scale=2), nullable=False, server_default="0"),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "validated",
                "matched",
                "partial",
                "mismatch",
                "needs_approval",
                "approved",
                "posted",
                "rejected",
                name="invoice_status",
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("payment_terms", sa.String(length=100), nullable=True),
        sa.Column("bank_account_name", sa.String(length=255), nullable=True),
        sa.Column("bank_account_number", sa.String(length=50), nullable=True),
        sa.Column("bank_ifsc", sa.String(length=11), nullable=True),
        sa.Column("bank_name", sa.String(length=100), nullable=True),
        sa.Column("defect_flags", JSONB(), nullable=False, server_default="{}"),
        sa.Column("extraction_confidence", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vendor_id", "invoice_number", name="uq_vendor_invoice_number"),
        sa.CheckConstraint("grand_total >= 0", name="ck_invoice_grand_total_positive"),
    )
    op.create_index("ix_invoice_vendor_date", "invoices", ["vendor_id", "invoice_date"], unique=False)
    op.create_index("ix_invoice_po_ref", "invoices", ["po_reference"], unique=False)
    op.create_index("ix_invoice_grn_ref", "invoices", ["grn_reference"], unique=False)
    op.create_index("ix_invoice_status_date", "invoices", ["status", "invoice_date"], unique=False)
    op.create_index("ix_invoice_irn", "invoices", ["irn"], unique=False)

    # invoice_lines table
    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("item_code", sa.String(length=50), nullable=True),
        sa.Column("item_description", sa.Text(), nullable=False),
        sa.Column("hsn_code", sa.String(length=8), nullable=False),
        sa.Column("uom", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=15, scale=3), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("discount_percent", sa.Numeric(precision=5, scale=2), nullable=False, server_default="0"),
        sa.Column("tax_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("tax_type", sa.Enum("CGST", "SGST", "IGST", "CESS", name="tax_type"), nullable=False),
        sa.Column("taxable_value", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("cgst_amount", sa.Numeric(precision=15, scale=2), nullable=False, server_default="0"),
        sa.Column("sgst_amount", sa.Numeric(precision=15, scale=2), nullable=False, server_default="0"),
        sa.Column("igst_amount", sa.Numeric(precision=15, scale=2), nullable=False, server_default="0"),
        sa.Column("cess_amount", sa.Numeric(precision=15, scale=2), nullable=False, server_default="0"),
        sa.Column("tax_amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("po_line_id", sa.Integer(), nullable=True),
        sa.Column("grn_line_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["po_line_id"], ["po_lines.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["grn_line_id"], ["grn_lines.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_id", "line_number", name="uq_invoice_line_number"),
        sa.CheckConstraint("quantity > 0", name="ck_inv_line_qty_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_inv_line_price_nonneg"),
        sa.CheckConstraint("tax_rate >= 0", name="ck_inv_line_tax_rate_nonneg"),
    )

    # approvals table
    op.create_table(
        "approvals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("approver_id", sa.String(length=100), nullable=True),
        sa.Column("approver_name", sa.String(length=100), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "approved", "rejected", "escalated", name="approval_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("approval_token", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_id", "level", name="uq_approval_invoice_level"),
    )
    op.create_index("ix_approval_token", "approvals", ["approval_token"], unique=False)
    op.create_index("ix_approval_idempotency", "approvals", ["idempotency_key"], unique=False)

    # posting_ledger table
    op.create_table(
        "posting_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("response", JSONB(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_posting_invoice_action", "posting_ledger", ["invoice_id", "action"], unique=False)

    # audit_log table
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=True),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("previous_hash", sa.String(length=64), nullable=True),
        sa.Column("current_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_entity", "audit_log", ["entity_type", "entity_id"], unique=False)
    op.create_index("ix_audit_created", "audit_log", ["created_at"], unique=False)

    # outbox table
    op.create_table(
        "outbox",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("message_type", sa.String(length=50), nullable=False),
        sa.Column("recipient", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outbox_status_scheduled", "outbox", ["status", "scheduled_at"], unique=False)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index("ix_outbox_status_scheduled", table_name="outbox")
    op.drop_table("outbox")

    op.drop_index("ix_audit_created", table_name="audit_log")
    op.drop_index("ix_audit_entity", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("ix_posting_invoice_action", table_name="posting_ledger")
    op.drop_table("posting_ledger")

    op.drop_index("ix_approval_idempotency", table_name="approvals")
    op.drop_index("ix_approval_token", table_name="approvals")
    op.drop_table("approvals")

    op.drop_table("invoice_lines")
    op.drop_index("ix_invoice_irn", table_name="invoices")
    op.drop_index("ix_invoice_status_date", table_name="invoices")
    op.drop_index("ix_invoice_grn_ref", table_name="invoices")
    op.drop_index("ix_invoice_po_ref", table_name="invoices")
    op.drop_index("ix_invoice_vendor_date", table_name="invoices")
    op.drop_table("invoices")

    op.drop_table("grn_lines")
    op.drop_index("ix_grn_vendor_date", table_name="goods_receipts")
    op.drop_index("ix_grn_po_date", table_name="goods_receipts")
    op.drop_table("goods_receipts")

    op.drop_table("po_lines")
    op.drop_index("ix_po_vendor_date", table_name="purchase_orders")
    op.drop_table("purchase_orders")

    op.drop_index("ix_vendors_gstin_active", table_name="vendors")
    op.drop_table("vendors")

    # Drop enum types
    sa.Enum(name="grn_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="po_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="approval_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="invoice_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="tax_type").drop(op.get_bind(), checkfirst=True)
