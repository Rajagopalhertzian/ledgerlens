"""Authentication for ERP MCP server (bearer tokens with scopes)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from .approval_token import init_token_manager


@dataclass
class TokenClaims:
    """JWT token claims."""

    sub: str  # subject (client ID)
    scopes: list[str]  # e.g., ["erp.read", "erp.write"]
    exp: int  # expiration timestamp
    iat: int  # issued at timestamp
    client_name: str | None = None


class AuthManager:
    """Manages JWT bearer token authentication."""

    def __init__(self, secret_key: str, algorithm: str = "HS256", access_token_ttl_minutes: int = 60):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_ttl_minutes = access_token_ttl_minutes
        # Initialize approval token manager with same secret
        init_token_manager(secret_key)

    def create_access_token(self, client_id: str, scopes: list[str], client_name: str | None = None) -> str:
        """Create a new access token."""
        now = datetime.now(UTC)
        exp = now + timedelta(minutes=self.access_token_ttl_minutes)

        claims = {"sub": client_id, "scopes": scopes, "exp": int(exp.timestamp()), "iat": int(now.timestamp())}

        if client_name:
            claims["client_name"] = client_name

        return jwt.encode(claims, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> TokenClaims | None:
        """Verify a bearer token and return claims."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm], options={"verify_exp": True})
            return TokenClaims(
                sub=payload["sub"],
                scopes=payload["scopes"],
                exp=payload["exp"],
                iat=payload["iat"],
                client_name=payload.get("client_name"),
            )
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def check_scope(self, claims: TokenClaims, required_scope: str) -> bool:
        """Check if token has required scope."""
        return required_scope in claims.scopes


# Scope constants
SCOPE_READ = "erp.read"
SCOPE_WRITE = "erp.write"

# Read tools require erp.read
READ_SCOPES = {SCOPE_READ}

# Write tools require erp.write (which implies erp.read)
WRITE_SCOPES = {SCOPE_WRITE, SCOPE_READ}


# Global auth manager
_auth_manager: AuthManager | None = None


def get_auth_manager() -> AuthManager:
    """Get the global auth manager."""
    global _auth_manager
    if _auth_manager is None:
        raise RuntimeError("Auth manager not initialized. Call init_auth_manager() first.")
    return _auth_manager


def init_auth_manager(secret_key: str, algorithm: str = "HS256", access_token_ttl_minutes: int = 60) -> AuthManager:
    """Initialize the global auth manager."""
    global _auth_manager
    _auth_manager = AuthManager(secret_key, algorithm, access_token_ttl_minutes)
    return _auth_manager


def verify_bearer_token(auth_header: str | None) -> TokenClaims | None:
    """Verify bearer token from Authorization header."""
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]  # Remove "Bearer "
    return get_auth_manager().verify_token(token)


def require_scope(claims: TokenClaims, scope: str) -> bool:
    """Check if claims have required scope."""
    return get_auth_manager().check_scope(claims, scope)
