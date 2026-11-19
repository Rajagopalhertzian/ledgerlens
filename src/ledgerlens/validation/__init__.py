"""Validation package for LedgerLens."""

from .bank import validate_bank_details, validate_bank_details_sync
from .dates import (
    validate_all_dates,
    validate_due_date,
    validate_grn_date,
    validate_invoice_date_plausibility,
    validate_invoice_not_before_po,
)
from .duplicates import (
    check_exact_duplicate,
    check_exact_duplicate_sync,
    check_near_duplicates,
    check_near_duplicates_sync,
)
from .gstin import (
    validate_gstin_checksum,
    validate_gstin_format,
    validate_gstin_full,
    validate_gstin_vendor_match,
    validate_gstin_vendor_match_sync,
)
from .irn import compute_irn, extract_fin_year, validate_irn, validate_irn_from_invoice
from .orchestrator import ValidationResult, ValidationSummary, run_all_validations, run_all_validations_sync
from .po_ref import validate_po_reference, validate_po_reference_sync
from .tax import (
    validate_grn_line_quantities,
    validate_invoice_totals,
    validate_line_tax_arithmetic,
    validate_po_line_arithmetic,
    validate_tax_type_vs_places,
)
from .text_layer import validate_text_layer_consistency, validate_text_layer_from_pdf

__all__ = [
    # GSTIN
    "validate_gstin_format",
    "validate_gstin_checksum",
    "validate_gstin_full",
    "validate_gstin_vendor_match",
    "validate_gstin_vendor_match_sync",
    # Tax
    "validate_tax_type_vs_places",
    "validate_line_tax_arithmetic",
    "validate_invoice_totals",
    "validate_po_line_arithmetic",
    "validate_grn_line_quantities",
    # IRN
    "compute_irn",
    "validate_irn",
    "validate_irn_from_invoice",
    "extract_fin_year",
    # Dates
    "validate_invoice_date_plausibility",
    "validate_invoice_not_before_po",
    "validate_due_date",
    "validate_grn_date",
    "validate_all_dates",
    # Duplicates
    "check_exact_duplicate",
    "check_near_duplicates",
    "check_exact_duplicate_sync",
    "check_near_duplicates_sync",
    # Bank
    "validate_bank_details",
    "validate_bank_details_sync",
    # PO Reference
    "validate_po_reference",
    "validate_po_reference_sync",
    # Text Layer
    "validate_text_layer_consistency",
    "validate_text_layer_from_pdf",
    # Orchestrator
    "run_all_validations",
    "run_all_validations_sync",
    "ValidationResult",
    "ValidationSummary",
]
