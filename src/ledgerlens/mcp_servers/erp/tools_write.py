"""Write tools for ERP MCP server."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ledgerlens.db.database import get_session
from ledgerlens.db.models import Approval, ApprovalStatus, AuditLog, Invoice, InvoiceStatus, Outbox, PostingLedger
from ledgerlens.mcp_servers.erp.approval_token import ApprovalTokenPayload, get_token_manager


@dataclass
class ToolResult:
    """Result of a tool call."""

    success: bool
    data: dict | None = None
    error: str | None = None


async def _verify_approval_token(
    approval_token: str, expected_action: str, expected_invoice_id: int, expected_amount: str
) -> ApprovalTokenPayload | None:
    """Verify HMAC-signed approval token."""
    from decimal import Decimal

    token_manager = get_token_manager()
    payload = token_manager.verify_token(approval_token)

    if not payload:
        return None

    if payload.action != expected_action:
        return None

    if payload.invoice_id != expected_invoice_id:
        return None

    # Compare amounts as Decimals to handle formatting differences (e.g., "118000" vs "118000.00")
    try:
        if Decimal(payload.amount) != Decimal(expected_amount):
            return None
    except Exception:
        # Fallback to string comparison if Decimal conversion fails
        if payload.amount != expected_amount:
            return None

    return payload


async def _audit_log(
    session: AsyncSession,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: int,
    before: dict | None = None,
    after: dict | None = None,
    success: bool = True,
    error_message: str | None = None,
) -> None:
    """Write audit log entry."""
    # Get previous hash for chaining
    prev_result = await session.execute(select(AuditLog.current_hash).order_by(AuditLog.id.desc()).limit(1))
    prev_hash = prev_result.scalar() or "0" * 64

    import hashlib
    import json

    payload = {
        "actor": actor,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "before": before,
        "after": after,
        "success": success,
        "error_message": error_message,
        "previous_hash": prev_hash,
    }

    data_json = json.dumps(payload, sort_keys=True, default=str)
    current_hash = hashlib.sha256(data_json.encode()).hexdigest()

    audit = AuditLog(
        event_type=action,  # Use action as event_type
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
        action=action,
        before_json=before,
        after_json=after,
        success=success,
        error_message=error_message,
        payload=payload,
        previous_hash=prev_hash,
        current_hash=current_hash,
    )
    session.add(audit)
    await session.flush()


# Tool: post_invoice
async def post_invoice(
    invoice_id: int, idempotency_key: str, approval_token: str, actor: str, session: AsyncSession | None = None
) -> ToolResult:
    """Post invoice to ERP (requires erp.write scope + valid HMAC approval token)."""
    if session is None:
        async with get_session() as session:
            return await _post_invoice(session, invoice_id, idempotency_key, approval_token, actor)
    else:
        return await _post_invoice(session, invoice_id, idempotency_key, approval_token, actor)


async def _post_invoice(
    session: AsyncSession, invoice_id: int, idempotency_key: str, approval_token: str, actor: str
) -> ToolResult:
    """Post invoice to ERP with idempotency and audit."""
    # Get invoice first to verify amount
    result = await session.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()

    if not invoice:
        await _audit_log(
            session, actor, "post_invoice", "invoice", invoice_id, success=False, error_message="Invoice not found"
        )
        return ToolResult(success=False, error=f"Invoice {invoice_id} not found")

    # Verify approval token with invoice amount
    token_payload = await _verify_approval_token(approval_token, "post_invoice", invoice_id, str(invoice.grand_total))
    if not token_payload:
        await _audit_log(
            session,
            actor,
            "post_invoice",
            "invoice",
            invoice_id,
            success=False,
            error_message="Invalid or expired approval token",
        )
        return ToolResult(success=False, error="Invalid or expired approval token")

    # Check idempotency key
    existing = await session.execute(select(PostingLedger).where(PostingLedger.idempotency_key == idempotency_key))
    existing_post = existing.scalar_one_or_none()

    if existing_post:
        # Idempotent replay - return success with original result
        return ToolResult(
            success=True,
            data={
                "posting_id": existing_post.id,
                "invoice_id": existing_post.invoice_id,
                "status": "already_posted",
                "original_posted_at": (existing_post.posted_at.isoformat() if existing_post.posted_at else None),
                "erp_document_id": existing_post.erp_document_id,
            },
        )

    # Check invoice status
    if invoice.status != InvoiceStatus.VALIDATED:
        await _audit_log(
            session,
            actor,
            "post_invoice",
            "invoice",
            invoice_id,
            before={"status": invoice.status.value},
            success=False,
            error_message=f"Invoice status {invoice.status.value} not valid for posting",
        )
        return ToolResult(success=False, error=f"Invoice status {invoice.status.value} not valid for posting")

    # Check approval status
    if invoice.approval_status != ApprovalStatus.APPROVED:
        await _audit_log(
            session,
            actor,
            "post_invoice",
            "invoice",
            invoice_id,
            before={"approval_status": invoice.approval_status.value},
            success=False,
            error_message=f"Invoice not approved: {invoice.approval_status.value}",
        )
        return ToolResult(success=False, error=f"Invoice not approved: {invoice.approval_status.value}")

    # Simulate ERP posting (in real implementation, call ERP API)
    erp_document_id = f"ERP-INV-{invoice.invoice_number}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

    # Update invoice status
    old_status = invoice.status
    invoice.status = InvoiceStatus.POSTED
    invoice.posted_at = datetime.now(UTC)
    invoice.erp_document_id = erp_document_id

    # Create posting ledger entry
    posting = PostingLedger(
        idempotency_key=idempotency_key,
        invoice_id=invoice_id,
        action="post_invoice",
        erp_document_id=erp_document_id,
        status="success",
        payload={"invoice_id": invoice_id, "idempotency_key": idempotency_key},
        response_payload={"erp_document_id": erp_document_id},
    )
    session.add(posting)

    # Create approval record
    approval = Approval(
        invoice_id=invoice_id,
        approver_id=actor,
        approver_name=actor,
        status=ApprovalStatus.APPROVED,
        comments=f"Posted via ERP MCP with token nonce {token_payload.nonce}",
    )
    session.add(approval)

    # Audit log
    await _audit_log(
        session,
        actor,
        "post_invoice",
        "invoice",
        invoice_id,
        before={"status": old_status.value},
        after={"status": InvoiceStatus.POSTED.value, "erp_document_id": erp_document_id},
        success=True,
    )

    await session.commit()

    return ToolResult(
        success=True,
        data={
            "posting_id": posting.id,
            "invoice_id": invoice_id,
            "status": "posted",
            "erp_document_id": erp_document_id,
            "posted_at": posting.posted_at.isoformat() if posting.posted_at else None,
        },
    )


# Tool: place_payment_hold
async def place_payment_hold(
    invoice_id: int,
    idempotency_key: str,
    approval_token: str,
    reason: str,
    hold_until: str | None = None,
    actor: str = "",
    session: AsyncSession | None = None,
) -> ToolResult:
    """Place payment hold on invoice (requires erp.write scope + valid HMAC approval token)."""
    if session is None:
        async with get_session() as session:
            return await _place_payment_hold(
                session, invoice_id, idempotency_key, approval_token, actor, reason, hold_until
            )
    else:
        return await _place_payment_hold(
            session, invoice_id, idempotency_key, approval_token, actor, reason, hold_until
        )


async def _place_payment_hold(
    session: AsyncSession,
    invoice_id: int,
    idempotency_key: str,
    approval_token: str,
    actor: str,
    reason: str,
    hold_until: str | None,
) -> ToolResult:
    """Place payment hold with idempotency and audit."""
    # Get invoice first to verify amount
    result = await session.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()

    if not invoice:
        await _audit_log(
            session,
            actor,
            "place_payment_hold",
            "invoice",
            invoice_id,
            success=False,
            error_message="Invoice not found",
        )
        return ToolResult(success=False, error=f"Invoice {invoice_id} not found")

    # Verify approval token with invoice amount
    token_payload = await _verify_approval_token(
        approval_token, "place_payment_hold", invoice_id, str(invoice.grand_total)
    )
    if not token_payload:
        await _audit_log(
            session,
            actor,
            "place_payment_hold",
            "invoice",
            invoice_id,
            success=False,
            error_message="Invalid or expired approval token",
        )
        return ToolResult(success=False, error="Invalid or expired approval token")

    # Check idempotency key
    existing = await session.execute(select(PostingLedger).where(PostingLedger.idempotency_key == idempotency_key))
    existing_post = existing.scalar_one_or_none()

    if existing_post:
        return ToolResult(
            success=True,
            data={
                "posting_id": existing_post.id,
                "invoice_id": existing_post.invoice_id,
                "status": "already_processed",
                "original_posted_at": (existing_post.posted_at.isoformat() if existing_post.posted_at else None),
            },
        )

    # Parse hold_until date
    if hold_until:
        try:
            datetime.fromisoformat(hold_until)
        except ValueError:
            return ToolResult(
                success=False, error="Invalid hold_until date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)"
            )

    # Create posting ledger entry
    posting = PostingLedger(
        idempotency_key=idempotency_key,
        invoice_id=invoice_id,
        action="place_payment_hold",
        status="success",
        payload={
            "invoice_id": invoice_id,
            "idempotency_key": idempotency_key,
            "reason": reason,
            "hold_until": hold_until,
        },
        response_payload={"hold_id": str(uuid.uuid4())},
    )
    session.add(posting)

    # Create approval record (level=2 for payment hold, level=1 is for posting)
    approval = Approval(
        invoice_id=invoice_id,
        level=2,
        approver_id=actor,
        approver_name=actor,
        status=ApprovalStatus.APPROVED,
        comments=f"Payment hold placed: {reason}. Nonce: {token_payload.nonce}",
    )
    session.add(approval)

    # Update invoice (add hold info to defect_flags or metadata)
    if not invoice.defect_flags:
        invoice.defect_flags = {}
    invoice.defect_flags["payment_hold"] = {
        "reason": reason,
        "hold_until": hold_until,
        "placed_by": actor,
        "placed_at": datetime.now(UTC).isoformat(),
        "nonce": token_payload.nonce,
    }

    # Audit log
    await _audit_log(
        session,
        actor,
        "place_payment_hold",
        "invoice",
        invoice_id,
        before={"defect_flags": invoice.defect_flags},
        after={"payment_hold": invoice.defect_flags.get("payment_hold")},
        success=True,
    )

    # Create outbox entry for notification
    outbox = Outbox(
        message_type="email",
        recipient=actor,  # In real impl, get vendor/AP email
        subject=f"Payment Hold Placed on Invoice {invoice.invoice_number}",
        body=(
            f"Payment hold placed on invoice {invoice.invoice_number} "
            f"(ID: {invoice_id}). Reason: {reason}. "
            f"Hold until: {hold_until or 'indefinite'}"
        ),
        payload={
            "invoice_id": invoice_id,
            "invoice_number": invoice.invoice_number,
            "reason": reason,
            "hold_until": hold_until,
            "actor": actor,
        },
        status="pending",
    )
    session.add(outbox)

    await session.commit()

    return ToolResult(
        success=True,
        data={
            "posting_id": posting.id,
            "invoice_id": invoice_id,
            "status": "hold_placed",
            "hold_id": posting.response_payload.get("hold_id") if posting.response_payload else None,
            "reason": reason,
            "hold_until": hold_until,
        },
    )
