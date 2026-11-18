"""LedgerLens Synthetic Data Generator.

This module provides tools for generating synthetic Indian GST invoice data
with ground truth for evaluation.
"""

from .generate import DataGenerator, main
from .gstin import (
    compute_checksum,
    generate_gstin,
    generate_random_gstin,
    parse_gstin,
    validate_gstin,
)
from .models import (
    Address,
    BankAccount,
    Currency,
    Decision,
    Defect,
    DefectType,
    GoodsReceipt,
    GRNLine,
    GroundTruth,
    Invoice,
    InvoiceLine,
    Manifest,
    POLine,
    PurchaseOrder,
    Split,
    StateCode,
    TaxBreakdown,
    TaxType,
    UoM,
    Vendor,
)
from .render import InvoiceRenderer, render_invoice

__all__ = [
    # Main
    "DataGenerator",
    "main",
    # GSTIN
    "compute_checksum",
    "generate_gstin",
    "generate_random_gstin",
    "parse_gstin",
    "validate_gstin",
    # Models
    "Address",
    "BankAccount",
    "Currency",
    "Decision",
    "Defect",
    "DefectType",
    "GoodsReceipt",
    "GRNLine",
    "GroundTruth",
    "Invoice",
    "InvoiceLine",
    "Manifest",
    "POLine",
    "PurchaseOrder",
    "Split",
    "StateCode",
    "TaxBreakdown",
    "TaxType",
    "UoM",
    "Vendor",
    # Render
    "InvoiceRenderer",
    "render_invoice",
]

__version__ = "1.0.0"
