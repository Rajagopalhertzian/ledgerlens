"""V12: Text-layer vs pixel consistency validation (when text layer exists)."""

from dataclasses import dataclass

from ..extraction.models import ExtractionResult


@dataclass
class ValidationResult:
    """Result of a validation check."""

    passed: bool
    message: str
    details: dict | None = None


def validate_text_layer_consistency(
    result: ExtractionResult, text_layer_text: str | None = None
) -> list[ValidationResult]:
    """V12: Validate text-layer vs pixel consistency.

    When a PDF has a text layer (digital PDF), compare extracted text
    with the text layer to detect potential tampering or OCR errors.
    """
    results = []

    if not text_layer_text:
        results.append(ValidationResult(True, "No text layer available for comparison", {"has_text_layer": False}))
        return results

    # Get full OCR text
    ocr_text = " ".join(token.text for token in result.ocr_tokens)

    # Normalize both texts
    text_layer_norm = normalize_text(text_layer_text)
    ocr_norm = normalize_text(ocr_text)

    # Calculate similarity
    from rapidfuzz import fuzz

    similarity = fuzz.ratio(text_layer_norm, ocr_norm) / 100.0

    if similarity < 0.7:
        results.append(
            ValidationResult(
                False,
                f"Low text-layer/OCR similarity: {similarity:.2f}",
                {
                    "similarity": similarity,
                    "text_layer_length": len(text_layer_text),
                    "ocr_length": len(ocr_text),
                    "text_layer_preview": text_layer_norm[:200],
                    "ocr_preview": ocr_norm[:200],
                },
            )
        )
    elif similarity < 0.9:
        results.append(
            ValidationResult(
                False,
                f"Moderate text-layer/OCR similarity: {similarity:.2f} (review recommended)",
                {"similarity": similarity, "text_layer_length": len(text_layer_text), "ocr_length": len(ocr_text)},
            )
        )
    else:
        results.append(
            ValidationResult(True, f"High text-layer/OCR similarity: {similarity:.2f}", {"similarity": similarity})
        )

    # Check for specific anomalies
    # 1. Missing text in OCR that's in text layer
    text_layer_words = set(text_layer_norm.split())
    ocr_words = set(ocr_norm.split())

    missing_in_ocr = text_layer_words - ocr_words
    extra_in_ocr = ocr_words - text_layer_words

    if len(missing_in_ocr) > len(text_layer_words) * 0.1:
        results.append(
            ValidationResult(
                False,
                f"OCR missing >10% of text-layer words: {len(missing_in_ocr)} words",
                {
                    "missing_count": len(missing_in_ocr),
                    "total_text_layer_words": len(text_layer_words),
                    "missing_sample": list(missing_in_ocr)[:20],
                },
            )
        )

    if len(extra_in_ocr) > len(text_layer_words) * 0.1:
        results.append(
            ValidationResult(
                False,
                f"OCR has >10% extra words not in text layer: {len(extra_in_ocr)} words",
                {
                    "extra_count": len(extra_in_ocr),
                    "total_text_layer_words": len(text_layer_words),
                    "extra_sample": list(extra_in_ocr)[:20],
                },
            )
        )

    return results


def normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    import re

    # Remove extra whitespace, lowercase
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def extract_text_from_pdf(pdf_path: str) -> str | None:
    """Extract text layer from PDF (placeholder for actual implementation).

    In production, use pdfplumber or pymupdf to extract text layer.
    """
    # This is a placeholder - actual implementation would use pdfplumber
    return None


def validate_text_layer_from_pdf(result: ExtractionResult, pdf_path: str) -> list[ValidationResult]:
    """Validate text layer by extracting from PDF."""
    text_layer = extract_text_from_pdf(pdf_path)
    return validate_text_layer_consistency(result, text_layer)
