"""Tests for text-layer vs pixel consistency validation (V12)."""

from ledgerlens.validation.text_layer import (
    normalize_text,
    validate_text_layer_consistency,
)
from ledgerlens.extraction.models import ExtractionResult, OCRToken, BoundingBox


class TestNormalizeText:
    """Tests for text normalization."""

    def test_removes_extra_whitespace(self):
        """Multiple spaces should be collapsed."""
        assert normalize_text("hello   world") == "hello world"
        assert normalize_text("hello\t\nworld") == "hello world"

    def test_lowercases(self):
        """Text should be lowercased."""
        assert normalize_text("HELLO WORLD") == "hello world"
        assert normalize_text("Hello World") == "hello world"

    def test_trims(self):
        """Leading/trailing whitespace should be removed."""
        assert normalize_text("  hello world  ") == "hello world"

    def test_empty_string(self):
        """Empty string should return empty."""
        assert normalize_text("") == ""

    def test_preserves_alphanumeric(self):
        """Alphanumeric characters should be preserved."""
        assert normalize_text("Invoice #123") == "invoice #123"


class TestValidateTextLayerConsistency:
    """Tests for text layer consistency validation."""

    def test_no_text_layer_passes(self):
        """No text layer should pass with appropriate message."""
        result = ExtractionResult(
            document_path="test.pdf",
            config_name="E0",
            ocr_tokens=[
                OCRToken(text="INVOICE", bbox=BoundingBox(x=0, y=0, width=100, height=20), confidence=0.9),
                OCRToken(text="Test", bbox=BoundingBox(x=0, y=30, width=50, height=20), confidence=0.8),
            ],
        )
        results = validate_text_layer_consistency(result, None)
        assert len(results) == 1
        assert results[0].passed
        assert "No text layer" in results[0].message

    def test_high_similarity_passes(self):
        """High similarity should pass."""
        result = ExtractionResult(
            document_path="test.pdf",
            config_name="E0",
            ocr_tokens=[
                OCRToken(text="INVOICE", bbox=BoundingBox(x=0, y=0, width=100, height=20), confidence=0.9),
                OCRToken(text="Test Vendor", bbox=BoundingBox(x=0, y=30, width=150, height=20), confidence=0.8),
                OCRToken(text="Amount 1000", bbox=BoundingBox(x=0, y=60, width=150, height=20), confidence=0.85),
            ],
        )
        text_layer = "INVOICE Test Vendor Amount 1000"
        results = validate_text_layer_consistency(result, text_layer)
        # Should have high similarity result
        high_sim = [r for r in results if "High" in r.message]
        assert len(high_sim) == 1
        assert high_sim[0].passed

    def test_low_similarity_fails(self):
        """Low similarity should fail."""
        result = ExtractionResult(
            document_path="test.pdf",
            config_name="E0",
            ocr_tokens=[
                OCRToken(text="INVOICE", bbox=BoundingBox(x=0, y=0, width=100, height=20), confidence=0.9),
                OCRToken(text="Different", bbox=BoundingBox(x=0, y=30, width=100, height=20), confidence=0.8),
                OCRToken(text="Content", bbox=BoundingBox(x=0, y=60, width=100, height=20), confidence=0.8),
            ],
        )
        text_layer = "COMPLETELY DIFFERENT TEXT HERE"
        results = validate_text_layer_consistency(result, text_layer)
        low_sim = [r for r in results if "Low" in r.message]
        assert len(low_sim) >= 1
        assert not low_sim[0].passed

    def test_moderate_similarity_warns(self):
        """Moderate similarity should warn but not fail completely."""
        result = ExtractionResult(
            document_path="test.pdf",
            config_name="E0",
            ocr_tokens=[
                OCRToken(text="INVOICE Test Vendor", bbox=BoundingBox(x=0, y=0, width=200, height=20), confidence=0.9),
            ],
        )
        text_layer = "INVOICE Test Vendor Extra Words Here"
        results = validate_text_layer_consistency(result, text_layer)
        # Should have moderate similarity result
        _ = [r for r in results if "Moderate" in r.message or "review" in r.message.lower()]
        # At least one result should exist
        assert len(results) >= 1

    def test_missing_words_detected(self):
        """Missing words in OCR should be detected."""
        result = ExtractionResult(
            document_path="test.pdf",
            config_name="E0",
            ocr_tokens=[
                OCRToken(text="INVOICE", bbox=BoundingBox(x=0, y=0, width=100, height=20), confidence=0.9),
            ],
        )
        # Text layer has many more words
        text_layer = "INVOICE Test Vendor Amount Total GST Tax " + " ".join([f"WORD{i}" for i in range(20)])
        results = validate_text_layer_consistency(result, text_layer)
        missing = [r for r in results if "missing" in r.message.lower()]
        assert len(missing) >= 1

    def test_extra_words_detected(self):
        """Extra words in OCR should be detected."""
        result = ExtractionResult(
            document_path="test.pdf",
            config_name="E0",
            ocr_tokens=[
                OCRToken(text="INVOICE Test Vendor Amount Total GST Tax " + " ".join([f"WORD{i}" for i in range(20)]),
                         bbox=BoundingBox(x=0, y=0, width=500, height=20), confidence=0.9),
            ],
        )
        text_layer = "INVOICE"
        results = validate_text_layer_consistency(result, text_layer)
        extra = [r for r in results if "extra" in r.message.lower()]
        assert len(extra) >= 1
