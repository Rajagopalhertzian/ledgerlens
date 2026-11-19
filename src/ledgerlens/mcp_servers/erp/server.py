"""ERP MCP Server - Streamable HTTP transport with bearer auth."""

import os
from contextlib import asynccontextmanager
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .approval_token import init_token_manager
from .auth import SCOPE_READ, SCOPE_WRITE, TokenClaims, init_auth_manager, require_scope, verify_bearer_token
from .tools_read import (
    check_duplicate,
    find_vendor_by_gstin,
    get_grn,
    get_invoice_history,
    get_po,
    get_vendor,
    search_pos,
)
from .tools_write import place_payment_hold, post_invoice


# Request/Response models for MCP tools
class FindVendorByGstinRequest(BaseModel):
    gstin: str


class GetVendorRequest(BaseModel):
    vendor_id: int


class GetPoRequest(BaseModel):
    po_id: int


class SearchPosRequest(BaseModel):
    vendor_gstin: str | None = None
    po_number: str | None = None
    status: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    limit: int = 50
    offset: int = 0


class GetGrnRequest(BaseModel):
    grn_id: int


class GetInvoiceHistoryRequest(BaseModel):
    vendor_gstin: str | None = None
    vendor_id: int | None = None
    status: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    limit: int = 50
    offset: int = 0


class CheckDuplicateRequest(BaseModel):
    vendor_gstin: str
    invoice_number: str
    invoice_date: str
    doc_type: str = "INV"


class PostInvoiceRequest(BaseModel):
    invoice_id: int
    idempotency_key: str
    approval_token: str


class PlacePaymentHoldRequest(BaseModel):
    invoice_id: int
    idempotency_key: str
    approval_token: str
    reason: str
    hold_until: str | None = None


class ToolResponse(BaseModel):
    success: bool
    data: dict | None = None
    error: str | None = None


# Authentication dependency
async def get_claims(authorization: str | None = Header(None)) -> TokenClaims:
    """Extract and verify bearer token claims."""
    claims = verify_bearer_token(authorization)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")
    return claims


async def require_read_scope(claims: Annotated[TokenClaims, Depends(get_claims)]) -> TokenClaims:
    """Require erp.read scope."""
    if not require_scope(claims, SCOPE_READ):
        raise HTTPException(status_code=403, detail="Insufficient scope: requires erp.read")
    return claims


async def require_write_scope(claims: Annotated[TokenClaims, Depends(get_claims)]) -> TokenClaims:
    """Require erp.write scope."""
    if not require_scope(claims, SCOPE_WRITE):
        raise HTTPException(status_code=403, detail="Insufficient scope: requires erp.write")
    return claims


# Initialize auth and token managers
def init_managers():
    """Initialize auth and token managers from environment."""
    secret_key = os.getenv("MCP_SECRET_KEY")
    if not secret_key:
        raise RuntimeError("MCP_SECRET_KEY environment variable not set")

    # Only initialize if not already initialized
    from .approval_token import get_token_manager
    from .auth import get_auth_manager

    try:
        get_auth_manager()
    except RuntimeError:
        init_auth_manager(secret_key)

    try:
        get_token_manager()
    except RuntimeError:
        init_token_manager(secret_key)


# Create FastAPI app
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_managers()
    yield


app = FastAPI(
    title="LedgerLens ERP MCP Server",
    description="MCP Server for ERP operations with bearer auth and HMAC approval tokens",
    version="1.0.0",
    lifespan=lifespan,
)


# Health check
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "ledgerlens-erp-mcp"}


# Read tools (require erp.read scope)
@app.post("/tools/find_vendor_by_gstin", response_model=ToolResponse)
async def tool_find_vendor_by_gstin(
    request: FindVendorByGstinRequest, claims: Annotated[TokenClaims, Depends(require_read_scope)]
):
    result = await find_vendor_by_gstin(request.gstin)
    return ToolResponse(success=result.success, data=result.data, error=result.error)


@app.post("/tools/get_vendor", response_model=ToolResponse)
async def tool_get_vendor(request: GetVendorRequest, claims: Annotated[TokenClaims, Depends(require_read_scope)]):
    result = await get_vendor(request.vendor_id)
    return ToolResponse(success=result.success, data=result.data, error=result.error)


@app.post("/tools/get_po", response_model=ToolResponse)
async def tool_get_po(request: GetPoRequest, claims: Annotated[TokenClaims, Depends(require_read_scope)]):
    result = await get_po(request.po_id)
    return ToolResponse(success=result.success, data=result.data, error=result.error)


@app.post("/tools/search_pos", response_model=ToolResponse)
async def tool_search_pos(request: SearchPosRequest, claims: Annotated[TokenClaims, Depends(require_read_scope)]):
    result = await search_pos(
        vendor_gstin=request.vendor_gstin,
        po_number=request.po_number,
        status=request.status,
        date_from=request.date_from,
        date_to=request.date_to,
        limit=request.limit,
        offset=request.offset,
    )
    return ToolResponse(success=result.success, data=result.data, error=result.error)


@app.post("/tools/get_grn", response_model=ToolResponse)
async def tool_get_grn(request: GetGrnRequest, claims: Annotated[TokenClaims, Depends(require_read_scope)]):
    result = await get_grn(request.grn_id)
    return ToolResponse(success=result.success, data=result.data, error=result.error)


@app.post("/tools/get_invoice_history", response_model=ToolResponse)
async def tool_get_invoice_history(
    request: GetInvoiceHistoryRequest, claims: Annotated[TokenClaims, Depends(require_read_scope)]
):
    result = await get_invoice_history(
        vendor_gstin=request.vendor_gstin,
        vendor_id=request.vendor_id,
        status=request.status,
        date_from=request.date_from,
        date_to=request.date_to,
        limit=request.limit,
        offset=request.offset,
    )
    return ToolResponse(success=result.success, data=result.data, error=result.error)


@app.post("/tools/check_duplicate", response_model=ToolResponse)
async def tool_check_duplicate(
    request: CheckDuplicateRequest, claims: Annotated[TokenClaims, Depends(require_read_scope)]
):
    result = await check_duplicate(
        vendor_gstin=request.vendor_gstin,
        invoice_number=request.invoice_number,
        invoice_date=request.invoice_date,
        doc_type=request.doc_type,
    )
    return ToolResponse(success=result.success, data=result.data, error=result.error)


# Write tools (require erp.write scope + HMAC approval token)
@app.post("/tools/post_invoice", response_model=ToolResponse)
async def tool_post_invoice(request: PostInvoiceRequest, claims: Annotated[TokenClaims, Depends(require_write_scope)]):
    result = await post_invoice(
        invoice_id=request.invoice_id,
        idempotency_key=request.idempotency_key,
        approval_token=request.approval_token,
        actor=claims.sub,
    )
    return ToolResponse(success=result.success, data=result.data, error=result.error)


@app.post("/tools/place_payment_hold", response_model=ToolResponse)
async def tool_place_payment_hold(
    request: PlacePaymentHoldRequest, claims: Annotated[TokenClaims, Depends(require_write_scope)]
):
    result = await place_payment_hold(
        invoice_id=request.invoice_id,
        idempotency_key=request.idempotency_key,
        approval_token=request.approval_token,
        reason=request.reason,
        hold_until=request.hold_until,
        actor=claims.sub,
    )
    return ToolResponse(success=result.success, data=result.data, error=result.error)


# Token generation endpoint (for testing/admin)
class CreateTokenRequest(BaseModel):
    client_id: str
    scopes: list[str]
    client_name: str | None = None


class CreateTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int


@app.post("/admin/create_token", response_model=CreateTokenResponse)
async def create_token(request: CreateTokenRequest, authorization: str | None = Header(None)):
    """Create a new access token (admin only - requires erp.write scope)."""
    claims = verify_bearer_token(authorization)
    if not claims or not require_scope(claims, SCOPE_WRITE):
        raise HTTPException(status_code=403, detail="Admin access required")

    from .auth import get_auth_manager

    auth_manager = get_auth_manager()

    token = auth_manager.create_access_token(
        client_id=request.client_id, scopes=request.scopes, client_name=request.client_name
    )

    return CreateTokenResponse(access_token=token, expires_in=auth_manager.access_token_ttl_minutes * 60)


# Approval token generation endpoint (for testing)
class CreateApprovalTokenRequest(BaseModel):
    invoice_id: int
    action: str  # "post_invoice" or "place_payment_hold"
    amount: str
    idempotency_key: str
    ttl_seconds: int = 300


class CreateApprovalTokenResponse(BaseModel):
    approval_token: str
    expires_in: int


@app.post("/admin/create_approval_token", response_model=CreateApprovalTokenResponse)
async def create_approval_token(request: CreateApprovalTokenRequest, authorization: str | None = Header(None)):
    """Create an HMAC approval token (admin only - requires erp.write scope)."""
    claims = verify_bearer_token(authorization)
    if not claims or not require_scope(claims, SCOPE_WRITE):
        raise HTTPException(status_code=403, detail="Admin access required")

    from .approval_token import get_token_manager

    token_manager = get_token_manager()

    # Override TTL if provided
    original_ttl = token_manager.token_ttl_seconds
    if request.ttl_seconds != original_ttl:
        token_manager.token_ttl_seconds = request.ttl_seconds

    try:
        token = token_manager.create_token(
            invoice_id=request.invoice_id,
            action=request.action,
            amount=request.amount,
            idempotency_key=request.idempotency_key,
        )
        return CreateApprovalTokenResponse(approval_token=token, expires_in=request.ttl_seconds)
    finally:
        token_manager.token_ttl_seconds = original_ttl


# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"success": False, "error": exc.detail})


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"success": False, "error": "Internal server error"})


def main():
    """Run the MCP server."""
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8000"))

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
