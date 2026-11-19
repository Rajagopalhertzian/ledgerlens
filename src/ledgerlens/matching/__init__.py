"""Matching package for LedgerLens."""

from .config import get_hsn_config, load_matching_config
from .entity import resolve_po, resolve_po_sync, resolve_vendor, resolve_vendor_sync
from .models import (
    Discrepancy,
    LineMatchResult,
    LineMatchStatus,
    MatchingConfig,
    MatchResult,
    MatchStatus,
    POCandidate,
    VendorMatchResult,
)
from .three_way import match_invoice_po_grn, normalize_uom

__all__ = [
    # Models
    "MatchStatus",
    "LineMatchStatus",
    "Discrepancy",
    "LineMatchResult",
    "MatchResult",
    "MatchingConfig",
    "POCandidate",
    "VendorMatchResult",
    # Entity resolution
    "resolve_vendor",
    "resolve_po",
    "resolve_vendor_sync",
    "resolve_po_sync",
    # Three-way matching
    "match_invoice_po_grn",
    "normalize_uom",
    # Config
    "load_matching_config",
    "get_hsn_config",
]
