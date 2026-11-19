"""Contract tests for ERP MCP Server."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from ledgerlens.db.database import drop_db, get_session, init_db
from ledgerlens.db.models import (
    ApprovalStatus,
    GoodsReceipt,
    GRNLine,
    GRNStatus,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    POLine,
    POStatus,
    PurchaseOrder,
    TaxType,
    Vendor,
)
from ledgerlens.mcp_servers.erp.approval_token import init_token_manager
from ledgerlens.mcp_servers.erp.auth import SCOPE_READ, SCOPE_WRITE, init_auth_manager
from ledgerlens.mcp_servers.erp.server import app

# Test configuration
TEST_SECRET = "test-secret-key-for-testing-only-32bytes!!"
TEST_CLIENT_ID = "test-client"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    """Set up test database."""
    import os

    # Use shared in-memory SQLite for tests - need uri=true for query parameters
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///file:test.db?mode=memory&cache=shared&uri=true"
    os.environ["MCP_SECRET_KEY"] = TEST_SECRET

    init_auth_manager(TEST_SECRET)
    init_token_manager(TEST_SECRET)

    await init_db()
    yield
    await drop_db()


@pytest_asyncio.fixture
async def client():
    """Create test client."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_headers():
    """Create auth headers with test token."""
    from ledgerlens.mcp_servers.erp.auth import get_auth_manager

    auth_manager = get_auth_manager()

    # Create token with both scopes
    token = auth_manager.create_access_token(
        client_id=TEST_CLIENT_ID, scopes=[SCOPE_READ, SCOPE_WRITE], client_name="Test Client"
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def read_only_headers():
    """Create auth headers with read-only token."""
    from ledgerlens.mcp_servers.erp.auth import get_auth_manager

    auth_manager = get_auth_manager()

    token = auth_manager.create_access_token(
        client_id="read-only-client", scopes=[SCOPE_READ], client_name="Read Only Client"
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="session")
async def seed_data():
    """Seed test data (session-scoped to avoid duplicates)."""
    async with get_session() as session:
        # Create vendor
        vendor = Vendor(
            gstin="29AAACA1234A1Z5",
            legal_name="Test Vendor Pvt Ltd",
            trade_name="Test Vendor",
            address_line1="123 Test Street",
            city="Bangalore",
            state_code="29",
            pincode="560001",
            country="India",
            bank_account_name="Test Vendor Pvt Ltd",
            bank_account_number="1234567890",
            bank_ifsc="TEST0001234",
            bank_name="Test Bank",
            contact_person="John Doe",
            contact_email="john@testvendor.com",
            contact_phone="+91-9876543210",
            pan="AAACA1234A",
            is_active=True,
        )
        session.add(vendor)
        await session.flush()
        vendor_id = vendor.id

        # Create PO
        po = PurchaseOrder(
            po_number="PO-2024-001",
            vendor_id=vendor_id,
            po_date=date(2024, 1, 15),
            delivery_date=date(2024, 2, 15),
            buyer_gstin="29BBBCB5678B2Z6",
            buyer_name="Test Buyer Ltd",
            buyer_address="456 Buyer Ave, Mumbai",
            buyer_state_code="27",
            place_of_supply="27",
            status=POStatus.OPEN,
            currency="INR",
            subtotal=Decimal("100000"),
            total_tax=Decimal("18000"),
            grand_total=Decimal("118000"),
            notes="Test PO",
        )
        session.add(po)
        await session.flush()
        po_id = po.id

        # Create PO line
        po_line = POLine(
            po_id=po_id,
            line_number=1,
            item_code="ITEM-001",
            item_description="Test Item",
            hsn_code="8471",
            uom="PCS",
            quantity=Decimal("100"),
            unit_price=Decimal("1000"),
            discount_percent=Decimal("0"),
            tax_rate=Decimal("18"),
            tax_type=TaxType.IGST,
            taxable_value=Decimal("100000"),
            tax_amount=Decimal("18000"),
            line_total=Decimal("118000"),
        )
        session.add(po_line)

        # Create GRN
        grn = GoodsReceipt(
            grn_number="GRN-2024-001",
            po_id=po_id,
            vendor_id=vendor_id,
            grn_date=date(2024, 2, 10),
            status=GRNStatus.COMPLETE,
            received_by="Warehouse Manager",
            notes="Received in good condition",
        )
        session.add(grn)
        await session.flush()
        grn_id = grn.id

        # Create GRN line
        grn_line = GRNLine(
            grn_id=grn_id,
            line_number=1,
            po_line_id=po_line.id,
            quantity_received=Decimal("100"),
            quantity_accepted=Decimal("100"),
            quantity_rejected=Decimal("0"),
            notes="",
        )
        session.add(grn_line)

        # Create Invoice
        invoice = Invoice(
            invoice_number="INV-2024-001",
            vendor_id=vendor_id,
            invoice_date=date(2024, 2, 12),
            due_date=date(2024, 3, 14),
            buyer_gstin="29BBBCB5678B2Z6",
            buyer_name="Test Buyer Ltd",
            buyer_address="456 Buyer Ave, Mumbai",
            buyer_state_code="27",
            place_of_supply="27",
            status=InvoiceStatus.VALIDATED,
            approval_status=ApprovalStatus.APPROVED,
            currency="INR",
            subtotal=Decimal("100000"),
            total_tax=Decimal("18000"),
            grand_total=Decimal("118000"),
            po_reference="PO-2024-001",
            grn_reference="GRN-2024-001",
            extraction_confidence=Decimal("0.95"),
        )
        session.add(invoice)
        await session.flush()
        invoice_id = invoice.id

        # Create Invoice line
        inv_line = InvoiceLine(
            invoice_id=invoice_id,
            line_number=1,
            item_code="ITEM-001",
            item_description="Test Item",
            hsn_code="8471",
            uom="PCS",
            quantity=Decimal("100"),
            unit_price=Decimal("1000"),
            discount_percent=Decimal("0"),
            tax_rate=Decimal("18"),
            tax_type=TaxType.IGST,
            taxable_value=Decimal("100000"),
            tax_amount=Decimal("18000"),
            line_total=Decimal("118000"),
            po_line_id=po_line.id,
            grn_line_id=grn_line.id,
        )
        session.add(inv_line)

        await session.commit()

        return {
            "vendor_id": vendor_id,
            "vendor_gstin": vendor.gstin,
            "po_id": po_id,
            "po_number": po.po_number,
            "po_line_id": po_line.id,
            "grn_id": grn_id,
            "grn_number": grn.grn_number,
            "grn_line_id": grn_line.id,
            "invoice_id": invoice_id,
            "invoice_number": invoice.invoice_number,
        }


async def create_validated_invoice(session, vendor_id, po_reference, grn_reference, invoice_number):
    """Create a fresh validated invoice for write tests."""
    from datetime import date
    from decimal import Decimal

    from ledgerlens.db.models import ApprovalStatus, Invoice, InvoiceLine, InvoiceStatus, TaxType

    invoice = Invoice(
        invoice_number=invoice_number,
        vendor_id=vendor_id,
        invoice_date=date(2024, 3, 1),
        due_date=date(2024, 4, 1),
        buyer_gstin="29BBBCB5678B2Z6",
        buyer_name="Test Buyer Ltd",
        buyer_address="456 Buyer Ave, Mumbai",
        buyer_state_code="27",
        place_of_supply="27",
        status=InvoiceStatus.VALIDATED,
        approval_status=ApprovalStatus.APPROVED,
        currency="INR",
        subtotal=Decimal("100000"),
        total_tax=Decimal("18000"),
        grand_total=Decimal("118000"),
        po_reference=po_reference,
        grn_reference=grn_reference,
        extraction_confidence=Decimal("0.95"),
    )
    session.add(invoice)
    await session.flush()

    # Create invoice line
    inv_line = InvoiceLine(
        invoice_id=invoice.id,
        line_number=1,
        item_code="ITEM-001",
        item_description="Test Item",
        hsn_code="8471",
        uom="PCS",
        quantity=Decimal("100"),
        unit_price=Decimal("1000"),
        discount_percent=Decimal("0"),
        tax_rate=Decimal("18"),
        tax_type=TaxType.IGST,
        taxable_value=Decimal("100000"),
        cgst_amount=Decimal("0"),
        sgst_amount=Decimal("0"),
        igst_amount=Decimal("18000"),
        cess_amount=Decimal("0"),
        tax_amount=Decimal("18000"),
        line_total=Decimal("118000"),
    )
    session.add(inv_line)
    await session.commit()
    await session.refresh(invoice)
    return invoice


# ============================================================================
# AUTHENTICATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_no_auth_fails(client):
    """Request without auth header should fail."""
    response = await client.post("/tools/get_vendor", json={"vendor_id": 1})
    assert response.status_code == 401
    assert response.json()["error"] == "Invalid or missing bearer token"


@pytest.mark.asyncio
async def test_invalid_token_fails(client):
    """Request with invalid token should fail."""
    response = await client.post(
        "/tools/get_vendor", json={"vendor_id": 1}, headers={"Authorization": "Bearer invalid-token"}
    )
    assert response.status_code == 401
    assert response.json()["error"] == "Invalid or missing bearer token"


@pytest.mark.asyncio
async def test_expired_token_fails(client):
    """Request with expired token should fail."""
    from ledgerlens.mcp_servers.erp.auth import get_auth_manager

    get_auth_manager()

    # Create token with very short TTL by manipulating exp
    import jwt

    now = datetime.utcnow()
    exp = now - timedelta(minutes=1)  # Expired 1 minute ago

    token = jwt.encode(
        {"sub": "test", "scopes": [SCOPE_READ], "exp": int(exp.timestamp()), "iat": int(now.timestamp())},
        TEST_SECRET,
        algorithm="HS256",
    )

    response = await client.post(
        "/tools/get_vendor", json={"vendor_id": 1}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


# ============================================================================
# SCOPE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_read_scope_denied_for_write_tools(client, read_only_headers, seed_data):
    """Read-only token should be denied for write tools."""
    # Create approval token for test
    from ledgerlens.mcp_servers.erp.approval_token import get_token_manager

    token_manager = get_token_manager()
    approval_token = token_manager.create_token(
        invoice_id=seed_data["invoice_id"],
        action="post_invoice",
        amount=str(seed_data.get("amount", "118000")),
        idempotency_key="test-idempotency-1",
    )

    response = await client.post(
        "/tools/post_invoice",
        json={
            "invoice_id": seed_data["invoice_id"],
            "idempotency_key": "test-idempotency-1",
            "approval_token": approval_token,
        },
        headers=read_only_headers,
    )
    assert response.status_code == 403
    assert "erp.write" in response.json()["error"]


@pytest.mark.asyncio
async def test_write_scope_allows_read_tools(client, auth_headers, seed_data):
    """Write token should allow read tools."""
    response = await client.post("/tools/get_vendor", json={"vendor_id": seed_data["vendor_id"]}, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["success"] is True


# ============================================================================
# READ TOOL TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_find_vendor_by_gstin(client, auth_headers, seed_data):
    """Test find_vendor_by_gstin tool."""
    response = await client.post(
        "/tools/find_vendor_by_gstin", json={"gstin": seed_data["vendor_gstin"]}, headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["vendor_id"] == seed_data["vendor_id"]
    assert data["data"]["gstin"] == seed_data["vendor_gstin"]


@pytest.mark.asyncio
async def test_find_vendor_by_gstin_not_found(client, auth_headers):
    """Test find_vendor_by_gstin with non-existent GSTIN."""
    response = await client.post("/tools/find_vendor_by_gstin", json={"gstin": "29AAAAA0000A1Z5"}, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "not found" in data["error"]


@pytest.mark.asyncio
async def test_get_vendor(client, auth_headers, seed_data):
    """Test get_vendor tool."""
    response = await client.post("/tools/get_vendor", json={"vendor_id": seed_data["vendor_id"]}, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["vendor_id"] == seed_data["vendor_id"]


@pytest.mark.asyncio
async def test_get_vendor_not_found(client, auth_headers):
    """Test get_vendor with non-existent ID."""
    response = await client.post("/tools/get_vendor", json={"vendor_id": 99999}, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "not found" in data["error"]


@pytest.mark.asyncio
async def test_get_po(client, auth_headers, seed_data):
    """Test get_po tool."""
    response = await client.post("/tools/get_po", json={"po_id": seed_data["po_id"]}, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["po_id"] == seed_data["po_id"]
    assert data["data"]["po_number"] == seed_data["po_number"]
    assert len(data["data"]["lines"]) == 1


@pytest.mark.asyncio
async def test_search_pos(client, auth_headers, seed_data):
    """Test search_pos tool."""
    response = await client.post(
        "/tools/search_pos", json={"vendor_gstin": seed_data["vendor_gstin"], "limit": 10}, headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["total"] >= 1
    assert len(data["data"]["pos"]) >= 1


@pytest.mark.asyncio
async def test_get_grn(client, auth_headers, seed_data):
    """Test get_grn tool."""
    response = await client.post("/tools/get_grn", json={"grn_id": seed_data["grn_id"]}, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["grn_id"] == seed_data["grn_id"]
    assert data["data"]["grn_number"] == seed_data["grn_number"]
    assert len(data["data"]["lines"]) == 1


@pytest.mark.asyncio
async def test_get_invoice_history(client, auth_headers, seed_data):
    """Test get_invoice_history tool."""
    response = await client.post(
        "/tools/get_invoice_history",
        json={"vendor_gstin": seed_data["vendor_gstin"], "limit": 10},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["total"] >= 1
    assert len(data["data"]["invoices"]) >= 1


@pytest.mark.asyncio
async def test_check_duplicate_exact(client, auth_headers, seed_data):
    """Test check_duplicate finds exact duplicate."""
    response = await client.post(
        "/tools/check_duplicate",
        json={
            "vendor_gstin": seed_data["vendor_gstin"],
            "invoice_number": seed_data["invoice_number"],
            "invoice_date": "2024-02-12",
            "doc_type": "INV",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["is_duplicate"] is True
    assert data["data"]["existing_invoice_id"] == seed_data["invoice_id"]


@pytest.mark.asyncio
async def test_check_duplicate_not_found(client, auth_headers, seed_data):
    """Test check_duplicate returns false for new invoice."""
    response = await client.post(
        "/tools/check_duplicate",
        json={
            "vendor_gstin": seed_data["vendor_gstin"],
            "invoice_number": "INV-NEW-001",
            "invoice_date": "2024-03-01",
            "doc_type": "INV",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["is_duplicate"] is False


# ============================================================================
# WRITE TOOL TESTS - APPROVAL TOKEN
# ============================================================================


@pytest.mark.asyncio
async def test_post_invoice_missing_approval_token(client, auth_headers, seed_data):
    """Test post_invoice fails without approval token."""
    response = await client.post(
        "/tools/post_invoice",
        json={
            "invoice_id": seed_data["invoice_id"],
            "idempotency_key": "test-idempotency-1",
            "approval_token": "",  # Missing
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "approval token" in data["error"].lower()


@pytest.mark.asyncio
async def test_post_invoice_invalid_approval_token(client, auth_headers, seed_data):
    """Test post_invoice fails with invalid approval token."""
    response = await client.post(
        "/tools/post_invoice",
        json={
            "invoice_id": seed_data["invoice_id"],
            "idempotency_key": "test-idempotency-1",
            "approval_token": "invalid.token",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "approval token" in data["error"].lower()


@pytest.mark.asyncio
async def test_post_invoice_wrong_action_in_token(client, auth_headers, seed_data):
    """Test post_invoice fails with token for wrong action."""
    from ledgerlens.mcp_servers.erp.approval_token import get_token_manager

    token_manager = get_token_manager()

    approval_token = token_manager.create_token(
        invoice_id=seed_data["invoice_id"],
        action="place_payment_hold",  # Wrong action
        amount="118000",
        idempotency_key="test-idempotency-1",
    )

    response = await client.post(
        "/tools/post_invoice",
        json={
            "invoice_id": seed_data["invoice_id"],
            "idempotency_key": "test-idempotency-1",
            "approval_token": approval_token,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "approval token" in data["error"].lower()


@pytest.mark.asyncio
async def test_post_invoice_wrong_invoice_in_token(client, auth_headers, seed_data):
    """Test post_invoice fails with token for different invoice."""
    from ledgerlens.mcp_servers.erp.approval_token import get_token_manager

    token_manager = get_token_manager()

    approval_token = token_manager.create_token(
        invoice_id=99999,  # Different invoice
        action="post_invoice",
        amount="118000",
        idempotency_key="test-idempotency-1",
    )

    response = await client.post(
        "/tools/post_invoice",
        json={
            "invoice_id": seed_data["invoice_id"],
            "idempotency_key": "test-idempotency-1",
            "approval_token": approval_token,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "approval token" in data["error"].lower()


@pytest.mark.asyncio
async def test_post_invoice_success(client, auth_headers, seed_data):
    """Test successful post_invoice."""
    from ledgerlens.db.database import get_session
    from ledgerlens.mcp_servers.erp.approval_token import get_token_manager

    # Create a fresh invoice for this test
    async with get_session() as session:
        invoice = await create_validated_invoice(
            session, seed_data["vendor_id"], seed_data["po_number"], seed_data["grn_number"], "INV-TEST-SUCCESS"
        )
        invoice_id = invoice.id

    token_manager = get_token_manager()
    approval_token = token_manager.create_token(
        invoice_id=invoice_id, action="post_invoice", amount="118000", idempotency_key="test-idempotency-success"
    )

    response = await client.post(
        "/tools/post_invoice",
        json={
            "invoice_id": invoice_id,
            "idempotency_key": "test-idempotency-success",
            "approval_token": approval_token,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["status"] == "posted"
    assert "erp_document_id" in data["data"]
    assert "posting_id" in data["data"]


@pytest.mark.asyncio
async def test_post_invoice_idempotent_replay(client, auth_headers, seed_data):
    """Test post_invoice is idempotent - replay returns same result."""
    from ledgerlens.db.database import get_session
    from ledgerlens.mcp_servers.erp.approval_token import get_token_manager

    # Create a fresh invoice for this test
    async with get_session() as session:
        invoice = await create_validated_invoice(
            session, seed_data["vendor_id"], seed_data["po_number"], seed_data["grn_number"], "INV-TEST-IDEMPOTENT"
        )
        invoice_id = invoice.id

    token_manager = get_token_manager()
    idempotency_key = "test-idempotency-replay"

    approval_token = token_manager.create_token(
        invoice_id=invoice_id, action="post_invoice", amount="118000", idempotency_key=idempotency_key
    )

    # First call
    response1 = await client.post(
        "/tools/post_invoice",
        json={"invoice_id": invoice_id, "idempotency_key": idempotency_key, "approval_token": approval_token},
        headers=auth_headers,
    )
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1["success"] is True
    assert data1["data"]["status"] == "posted"
    posting_id = data1["data"]["posting_id"]

    # Second call with same idempotency key (different token OK)
    approval_token2 = token_manager.create_token(
        invoice_id=invoice_id, action="post_invoice", amount="118000", idempotency_key=idempotency_key
    )

    response2 = await client.post(
        "/tools/post_invoice",
        json={"invoice_id": invoice_id, "idempotency_key": idempotency_key, "approval_token": approval_token2},
        headers=auth_headers,
    )
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["success"] is True
    assert data2["data"]["status"] == "already_posted"
    assert data2["data"]["posting_id"] == posting_id


@pytest.mark.asyncio
async def test_post_invoice_invoice_not_validated(client, auth_headers, seed_data):
    """Test post_invoice fails for non-validated invoice."""
    # Create a new invoice with DRAFT status
    async with get_session() as session:
        invoice = Invoice(
            invoice_number="INV-DRAFT-001",
            vendor_id=seed_data["vendor_id"],
            invoice_date=date(2024, 3, 1),
            due_date=date(2024, 4, 1),
            buyer_gstin="29BBBCB5678B2Z6",
            buyer_name="Test Buyer Ltd",
            buyer_address="456 Buyer Ave, Mumbai",
            buyer_state_code="27",
            place_of_supply="27",
            status=InvoiceStatus.DRAFT,  # Not validated
            approval_status=ApprovalStatus.PENDING,
            currency="INR",
            subtotal=Decimal("50000"),
            total_tax=Decimal("9000"),
            grand_total=Decimal("59000"),
        )
        session.add(invoice)
        await session.commit()
        await session.refresh(invoice)
        draft_invoice_id = invoice.id

    from ledgerlens.mcp_servers.erp.approval_token import get_token_manager

    token_manager = get_token_manager()

    approval_token = token_manager.create_token(
        invoice_id=draft_invoice_id, action="post_invoice", amount="59000", idempotency_key="test-draft-idempotency"
    )

    response = await client.post(
        "/tools/post_invoice",
        json={
            "invoice_id": draft_invoice_id,
            "idempotency_key": "test-draft-idempotency",
            "approval_token": approval_token,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "not valid for posting" in data["error"]


# ============================================================================
# PLACE PAYMENT HOLD TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_place_payment_hold_success(client, auth_headers, seed_data):
    """Test successful place_payment_hold."""
    from ledgerlens.db.database import get_session
    from ledgerlens.mcp_servers.erp.approval_token import get_token_manager

    # Create a fresh invoice for this test
    async with get_session() as session:
        invoice = await create_validated_invoice(
            session, seed_data["vendor_id"], seed_data["po_number"], seed_data["grn_number"], "INV-TEST-HOLD"
        )
        invoice_id = invoice.id

    token_manager = get_token_manager()
    approval_token = token_manager.create_token(
        invoice_id=invoice_id, action="place_payment_hold", amount="118000", idempotency_key="test-hold-idempotency"
    )

    response = await client.post(
        "/tools/place_payment_hold",
        json={
            "invoice_id": invoice_id,
            "idempotency_key": "test-hold-idempotency",
            "approval_token": approval_token,
            "reason": "Quality issue detected",
            "hold_until": "2024-04-01T00:00:00",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["status"] == "hold_placed"
    assert data["data"]["reason"] == "Quality issue detected"


@pytest.mark.asyncio
async def test_place_payment_hold_invalid_token(client, auth_headers, seed_data):
    """Test place_payment_hold fails with invalid token."""
    response = await client.post(
        "/tools/place_payment_hold",
        json={
            "invoice_id": seed_data["invoice_id"],
            "idempotency_key": "test-hold-idempotency-2",
            "approval_token": "invalid.token",
            "reason": "Test hold",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False


@pytest.mark.asyncio
async def test_place_payment_hold_wrong_action(client, auth_headers, seed_data):
    """Test place_payment_hold fails with post_invoice token."""
    from ledgerlens.mcp_servers.erp.approval_token import get_token_manager

    token_manager = get_token_manager()

    approval_token = token_manager.create_token(
        invoice_id=seed_data["invoice_id"],
        action="post_invoice",  # Wrong action
        amount="118000",
        idempotency_key="test-hold-idempotency-3",
    )

    response = await client.post(
        "/tools/place_payment_hold",
        json={
            "invoice_id": seed_data["invoice_id"],
            "idempotency_key": "test-hold-idempotency-3",
            "approval_token": approval_token,
            "reason": "Test hold",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False


@pytest.mark.asyncio
async def test_place_payment_hold_idempotent(client, auth_headers, seed_data):
    """Test place_payment_hold is idempotent."""
    from ledgerlens.db.database import get_session
    from ledgerlens.mcp_servers.erp.approval_token import get_token_manager

    # Create a fresh invoice for this test
    async with get_session() as session:
        invoice = await create_validated_invoice(
            session, seed_data["vendor_id"], seed_data["po_number"], seed_data["grn_number"], "INV-TEST-HOLD-IDEMPOTENT"
        )
        invoice_id = invoice.id

    token_manager = get_token_manager()
    idempotency_key = "test-hold-idempotency-replay"

    approval_token = token_manager.create_token(
        invoice_id=invoice_id, action="place_payment_hold", amount="118000", idempotency_key=idempotency_key
    )

    # First call
    response1 = await client.post(
        "/tools/place_payment_hold",
        json={
            "invoice_id": invoice_id,
            "idempotency_key": idempotency_key,
            "approval_token": approval_token,
            "reason": "Test hold",
        },
        headers=auth_headers,
    )
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1["success"] is True
    posting_id = data1["data"]["posting_id"]

    # Second call
    approval_token2 = token_manager.create_token(
        invoice_id=invoice_id, action="place_payment_hold", amount="118000", idempotency_key=idempotency_key
    )

    response2 = await client.post(
        "/tools/place_payment_hold",
        json={
            "invoice_id": invoice_id,
            "idempotency_key": idempotency_key,
            "approval_token": approval_token2,
            "reason": "Test hold",
        },
        headers=auth_headers,
    )
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["success"] is True
    assert data2["data"]["status"] == "already_processed"
    assert data2["data"]["posting_id"] == posting_id


# ============================================================================
# ADMIN ENDPOINT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_create_token_admin(client, auth_headers):
    """Test admin token creation."""
    response = await client.post(
        "/admin/create_token",
        json={"client_id": "new-client", "scopes": [SCOPE_READ], "client_name": "New Client"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == 3600  # 60 minutes


@pytest.mark.asyncio
async def test_create_token_admin_denied_for_read_only(client, read_only_headers):
    """Test admin token creation denied for read-only token."""
    response = await client.post(
        "/admin/create_token", json={"client_id": "new-client", "scopes": [SCOPE_READ]}, headers=read_only_headers
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_approval_token_admin(client, auth_headers, seed_data):
    """Test admin approval token creation."""
    response = await client.post(
        "/admin/create_approval_token",
        json={
            "invoice_id": seed_data["invoice_id"],
            "action": "post_invoice",
            "amount": "118000",
            "idempotency_key": "admin-test-key",
            "ttl_seconds": 300,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "approval_token" in data
    assert data["expires_in"] == 300

    # Verify the token works
    from ledgerlens.mcp_servers.erp.approval_token import get_token_manager

    token_manager = get_token_manager()
    payload = token_manager.verify_token(data["approval_token"])
    assert payload is not None
    assert payload.invoice_id == seed_data["invoice_id"]
    assert payload.action == "post_invoice"
    assert payload.amount == "118000"


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_endpoint(client):
    """Test health endpoint works without auth."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_invalid_json(client, auth_headers):
    """Test invalid JSON returns 422."""
    response = await client.post(
        "/tools/get_vendor", content="not json", headers={**auth_headers, "Content-Type": "application/json"}
    )
    assert response.status_code == 422


# ============================================================================
# AUDIT LOG TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_post_invoice_creates_audit_log(client, auth_headers, seed_data):
    """Test post_invoice creates audit log entry."""
    from ledgerlens.db.database import get_session
    from ledgerlens.mcp_servers.erp.approval_token import get_token_manager

    # Create a fresh invoice for this test
    async with get_session() as session:
        invoice = await create_validated_invoice(
            session, seed_data["vendor_id"], seed_data["po_number"], seed_data["grn_number"], "INV-TEST-AUDIT"
        )
        invoice_id = invoice.id

    token_manager = get_token_manager()
    idempotency_key = "test-audit-idempotency"
    approval_token = token_manager.create_token(
        invoice_id=invoice_id, action="post_invoice", amount="118000", idempotency_key=idempotency_key
    )

    response = await client.post(
        "/tools/post_invoice",
        json={"invoice_id": invoice_id, "idempotency_key": idempotency_key, "approval_token": approval_token},
        headers=auth_headers,
    )
    assert response.status_code == 200

    # Verify audit log was created
    async with get_session() as session:
        from sqlalchemy import desc, select

        from ledgerlens.db.models import AuditLog

        result = await session.execute(
            select(AuditLog)
            .where(
                AuditLog.entity_type == "invoice", AuditLog.entity_id == invoice_id, AuditLog.action == "post_invoice"
            )
            .order_by(desc(AuditLog.created_at))
            .limit(1)
        )
        audit = result.scalar_one_or_none()
        assert audit is not None
        assert audit.success is True
        assert audit.actor == TEST_CLIENT_ID


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
