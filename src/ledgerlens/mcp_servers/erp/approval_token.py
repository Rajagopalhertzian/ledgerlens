"""HMAC-signed approval tokens for ERP write operations."""

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


@dataclass
class ApprovalTokenPayload:
    """Payload for approval token."""

    invoice_id: int
    action: str  # "post_invoice", "place_payment_hold"
    amount: str  # Decimal as string
    idempotency_key: str
    expires_at: int  # Unix timestamp
    nonce: str


class ApprovalTokenManager:
    """Manages HMAC-signed approval tokens."""

    def __init__(self, secret_key: bytes, token_ttl_seconds: int = 300):
        """Initialize token manager.

        Args:
            secret_key: Secret key for HMAC (at least 32 bytes)
            token_ttl_seconds: Token time-to-live in seconds (default 5 minutes)
        """
        if len(secret_key) < 32:
            # Derive a proper key using HKDF
            hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"ledgerlens-approval-token")
            self.secret_key = hkdf.derive(secret_key)
        else:
            self.secret_key = secret_key[:32]
        self.token_ttl_seconds = token_ttl_seconds

    def create_token(
        self, invoice_id: int, action: str, amount: str, idempotency_key: str, nonce: str | None = None
    ) -> str:
        """Create a new approval token."""
        import secrets

        expires_at = int(time.time()) + self.token_ttl_seconds
        nonce = nonce or secrets.token_hex(16)

        payload = ApprovalTokenPayload(
            invoice_id=invoice_id,
            action=action,
            amount=amount,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            nonce=nonce,
        )

        # Serialize payload
        payload_json = json.dumps(
            {
                "invoice_id": payload.invoice_id,
                "action": payload.action,
                "amount": payload.amount,
                "idempotency_key": payload.idempotency_key,
                "expires_at": payload.expires_at,
                "nonce": payload.nonce,
            },
            separators=(",", ":"),
            sort_keys=True,
        )

        # Create HMAC signature
        signature = hmac.new(self.secret_key, payload_json.encode(), hashlib.sha256).digest()

        # Encode token as base64(payload).base64(signature)
        token = (
            base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip("=")
            + "."
            + base64.urlsafe_b64encode(signature).decode().rstrip("=")
        )

        return token

    def verify_token(self, token: str) -> ApprovalTokenPayload | None:
        """Verify an approval token and return payload if valid."""
        try:
            # Split token
            parts = token.split(".")
            if len(parts) != 2:
                return None

            payload_b64, signature_b64 = parts

            # Add padding if needed
            payload_b64 += "=" * (-len(payload_b64) % 4)
            signature_b64 += "=" * (-len(signature_b64) % 4)

            # Decode payload
            payload_json = base64.urlsafe_b64decode(payload_b64).decode()
            signature = base64.urlsafe_b64decode(signature_b64)

            # Verify HMAC
            expected_signature = hmac.new(self.secret_key, payload_json.encode(), hashlib.sha256).digest()

            if not hmac.compare_digest(signature, expected_signature):
                return None

            # Parse payload
            data = json.loads(payload_json)

            # Check expiration
            if data["expires_at"] < int(time.time()):
                return None

            return ApprovalTokenPayload(
                invoice_id=data["invoice_id"],
                action=data["action"],
                amount=data["amount"],
                idempotency_key=data["idempotency_key"],
                expires_at=data["expires_at"],
                nonce=data["nonce"],
            )

        except Exception:
            return None

    def is_valid_action(self, action: str) -> bool:
        """Check if action is valid for write operations."""
        return action in ("post_invoice", "place_payment_hold")


# Global token manager instance (initialized from config)
_token_manager: ApprovalTokenManager | None = None


def get_token_manager() -> ApprovalTokenManager:
    """Get the global token manager."""
    global _token_manager
    if _token_manager is None:
        raise RuntimeError("Token manager not initialized. Call init_token_manager() first.")
    return _token_manager


def init_token_manager(secret_key: str | bytes, token_ttl_seconds: int = 300) -> ApprovalTokenManager:
    """Initialize the global token manager."""
    global _token_manager
    if isinstance(secret_key, str):
        secret_key = secret_key.encode()
    _token_manager = ApprovalTokenManager(secret_key, token_ttl_seconds)
    return _token_manager
