"""Extraction package for LedgerLens.

Provides OCR, VLM, and text parsing backends with grounding validation,
calibrated confidence, and cascade routing.
"""

from .extractor import EXTRACTION_CONFIGS, ExtractionConfig, Extractor
from .models import (
    BoundingBox,
    CalibratedConfidence,
    EvidenceSpan,
    ExtractedField,
    ExtractionResult,
    FieldType,
    LineItem,
    OCRToken,
    ValidationResult,
)

__all__ = [
    "ExtractionResult",
    "ExtractedField",
    "LineItem",
    "BoundingBox",
    "EvidenceSpan",
    "OCRToken",
    "ValidationResult",
    "CalibratedConfidence",
    "Extractor",
    "ExtractionConfig",
    "EXTRACTION_CONFIGS",
    "FieldType",
]
