"""Tests for extraction module."""

from pathlib import Path

import pytest
from PIL import Image

from ledgerlens.extraction.adapters.ocr import MockOCR, OCRToken
from ledgerlens.extraction.adapters.text_parser import MockTextParser
from ledgerlens.extraction.calibration import (
    ConfidenceCalibrator,
    calibrate_extraction_result,
    compute_field_ece,
    extract_calibration_features,
    selective_prediction_curve,
)
from ledgerlens.extraction.extractor import EXTRACTION_CONFIGS, get_extractor
from ledgerlens.extraction.models import (
    BoundingBox,
    EvidenceSpan,
    ExtractedField,
    ExtractionResult,
    ExtractionSource,
    FieldType,
    LineItem,
)
from ledgerlens.extraction.validators import DeterministicValidators, GroundingValidator, run_all_validators


class TestModels:
    """Test extraction models."""

    def test_bounding_box(self):
        bbox = BoundingBox(x=10, y=20, width=100, height=50)
        assert bbox.center() == (60, 45)
        assert bbox.overlaps(BoundingBox(x=50, y=30, width=100, height=50))

    def test_ocr_token(self):
        token = OCRToken(text="INV001", bbox=BoundingBox(x=0, y=0, width=50, height=20), confidence=0.95)
        assert token.normalized_text() == "inv001"

    def test_evidence_span(self):
        evidence = EvidenceSpan(source=ExtractionSource.OCR, token_indices=[0, 1, 2])
        assert evidence.is_grounded()

        evidence2 = EvidenceSpan(source=ExtractionSource.VLM)
        assert not evidence2.is_grounded()

    def test_extracted_field(self):
        field = ExtractedField(
            field_type=FieldType.VENDOR_GSTIN,
            value="29ABCDE1234F1Z5",
            confidence=0.9,
            evidence=EvidenceSpan(source=ExtractionSource.OCR, token_indices=[0]),
            source=ExtractionSource.OCR,
        )
        assert field.field_type == FieldType.VENDOR_GSTIN
        assert field.grounded is False  # Default

    def test_line_item(self):
        item = LineItem(line_number=1)
        item.item_description = ExtractedField(
            field_type=FieldType.ITEM_DESCRIPTION,
            value="Test Item",
            confidence=0.8,
            evidence=EvidenceSpan(source=ExtractionSource.OCR),
            source=ExtractionSource.OCR,
        )
        fields = item.get_all_fields()
        assert len(fields) == 1

    def test_extraction_result(self):
        result = ExtractionResult(document_path="test.pdf", config_name="E1")
        result.vendor_name = ExtractedField(
            field_type=FieldType.VENDOR_NAME,
            value="Test Vendor",
            confidence=0.9,
            evidence=EvidenceSpan(source=ExtractionSource.OCR),
            source=ExtractionSource.OCR,
        )
        header = result.get_header_fields()
        assert FieldType.VENDOR_NAME in header


class TestOCRAdapters:
    """Test OCR adapters."""

    def test_mock_ocr(self):
        tokens = [
            OCRToken(text="INV001", bbox=BoundingBox(x=0, y=0, width=50, height=20), confidence=0.9),
            OCRToken(text="Test", bbox=BoundingBox(x=60, y=0, width=40, height=20), confidence=0.85),
        ]
        ocr = MockOCR(mock_tokens=tokens, mock_text="INV001 Test")

        result = ocr.extract(Path("dummy.png"))
        assert len(result) == 2
        assert result[0].text == "INV001"

        text = ocr.extract_full_text(Path("dummy.png"))
        assert text == "INV001 Test"


class TestValidators:
    """Test validators."""

    def test_grounding_validator(self):
        validator = GroundingValidator()

        # Create result with OCR tokens
        tokens = [
            OCRToken(text="INV001", bbox=BoundingBox(x=0, y=0, width=50, height=20), confidence=0.9),
            OCRToken(text="Test Vendor", bbox=BoundingBox(x=60, y=0, width=100, height=20), confidence=0.85),
        ]

        result = ExtractionResult(document_path="test.pdf", config_name="E1", ocr_tokens=tokens)
        result.vendor_name = ExtractedField(
            field_type=FieldType.VENDOR_NAME,
            value="Test Vendor",
            normalized_value="Test Vendor",
            confidence=0.9,
            evidence=EvidenceSpan(source=ExtractionSource.OCR),
            source=ExtractionSource.OCR,
        )

        validations = validator.validate(result)
        assert len(validations) > 0
        # Vendor name should be grounded
        vendor_val = validations[0]
        assert vendor_val.validator_name == "grounding"

    def test_deterministic_validators(self):
        validators = DeterministicValidators()

        result = ExtractionResult(document_path="test.pdf", config_name="E1")
        # Add minimal valid fields
        result.invoice_number = ExtractedField(
            field_type=FieldType.INVOICE_NUMBER,
            value="INV001",
            normalized_value="INV001",
            confidence=0.9,
            evidence=EvidenceSpan(source=ExtractionSource.OCR),
            source=ExtractionSource.OCR,
        )
        result.invoice_date = ExtractedField(
            field_type=FieldType.INVOICE_DATE,
            value="2024-01-15",
            normalized_value="2024-01-15",
            confidence=0.9,
            evidence=EvidenceSpan(source=ExtractionSource.OCR),
            source=ExtractionSource.OCR,
        )
        result.vendor_gstin = ExtractedField(
            field_type=FieldType.VENDOR_GSTIN,
            value="29ABCDE1234F1Z5",
            normalized_value="29ABCDE1234F1Z5",
            confidence=0.9,
            evidence=EvidenceSpan(source=ExtractionSource.OCR),
            source=ExtractionSource.OCR,
        )

        validations = validators.validate(result)
        assert len(validations) > 0

    def test_gstin_checksum(self):
        validators = DeterministicValidators()
        # Valid GSTIN (checksum = 3 for prefix 29ABCDE1234F1Z)
        assert validators._verify_gstin_checksum("29ABCDE1234F1Z3")
        # Invalid checksum
        assert not validators._verify_gstin_checksum("29ABCDE1234F1Z6")


class TestCalibration:
    """Test confidence calibration."""

    def test_confidence_calibrator_isotonic(self):
        calibrator = ConfidenceCalibrator(method="isotonic")
        # Perfect calibration data
        features = [[0.1], [0.2], [0.3], [0.7], [0.8], [0.9]]
        labels = [0, 0, 0, 1, 1, 1]

        calibrator.fit(features, labels)
        preds = calibrator.predict([[0.5], [0.9]])

        assert len(preds) == 2
        assert 0 <= preds[0] <= 1
        assert 0 <= preds[1] <= 1

    def test_confidence_calibrator_logistic(self):
        calibrator = ConfidenceCalibrator(method="logistic")
        features = [[0.1, 0.5], [0.2, 0.6], [0.8, 0.9], [0.9, 0.95]]
        labels = [0, 0, 1, 1]

        calibrator.fit(features, labels)
        preds = calibrator.predict([[0.5, 0.7], [0.9, 0.9]])

        assert len(preds) == 2

    def test_extract_calibration_features(self):
        field = ExtractedField(
            field_type=FieldType.VENDOR_GSTIN,
            value="29ABCDE1234F1Z5",
            confidence=0.9,
            evidence=EvidenceSpan(source=ExtractionSource.OCR, token_indices=[0]),
            source=ExtractionSource.OCR,
            grounded=True,
        )

        result = ExtractionResult(
            document_path="test.pdf",
            config_name="E1",
            ocr_tokens=[
                OCRToken(text="29ABCDE1234F1Z5", bbox=BoundingBox(x=0, y=0, width=100, height=20), confidence=0.95)
            ],
        )

        features = extract_calibration_features(field, result)
        assert len(features) == 6
        assert features[0] == 0.9  # raw confidence
        assert features[2] == 1.0  # grounded

    def test_heuristic_calibration(self):
        result = ExtractionResult(document_path="test.pdf", config_name="E1")
        result.vendor_name = ExtractedField(
            field_type=FieldType.VENDOR_NAME,
            value="Test Vendor",
            confidence=0.8,
            evidence=EvidenceSpan(source=ExtractionSource.OCR, token_indices=[0]),
            source=ExtractionSource.OCR,
            grounded=True,
        )
        result.ocr_tokens = [
            OCRToken(text="Test Vendor", bbox=BoundingBox(x=0, y=0, width=100, height=20), confidence=0.9)
        ]

        calibrated = calibrate_extraction_result(result)
        assert calibrated.vendor_name is not None
        assert calibrated.vendor_name.calibrated_confidence is not None
        assert calibrated.vendor_name.calibrated_confidence >= calibrated.vendor_name.confidence

    def test_compute_field_ece(self):
        # Create mock results and ground truth
        results = []
        ground_truth = []

        for i in range(10):
            result = ExtractionResult(document_path=f"test{i}.pdf", config_name="E1")
            result.vendor_name = ExtractedField(
                field_type=FieldType.VENDOR_NAME,
                value=f"Vendor{i}",
                confidence=0.7 + i * 0.02,
                calibrated_confidence=0.7 + i * 0.02,
                evidence=EvidenceSpan(source=ExtractionSource.OCR),
                source=ExtractionSource.OCR,
            )
            results.append(result)
            ground_truth.append({FieldType.VENDOR_NAME: f"Vendor{i}" if i % 2 == 0 else f"Other{i}"})

        ece = compute_field_ece(results, ground_truth, FieldType.VENDOR_NAME)
        assert 0 <= ece <= 1

    def test_selective_prediction_curve(self):
        results = []
        ground_truth = []

        for i in range(20):
            result = ExtractionResult(document_path=f"test{i}.pdf", config_name="E1")
            result.vendor_name = ExtractedField(
                field_type=FieldType.VENDOR_NAME,
                value=f"Vendor{i}",
                confidence=0.5 + i * 0.025,
                calibrated_confidence=0.5 + i * 0.025,
                evidence=EvidenceSpan(source=ExtractionSource.OCR),
                source=ExtractionSource.OCR,
            )
            results.append(result)
            ground_truth.append({FieldType.VENDOR_NAME: f"Vendor{i}" if i < 15 else f"Other{i}"})

        curve = selective_prediction_curve(results, ground_truth, FieldType.VENDOR_NAME, n_points=10)
        assert len(curve) == 10
        for coverage, precision in curve:
            assert 0 <= coverage <= 1
            assert 0 <= precision <= 1


class TestExtractor:
    """Test extractor pipeline."""

    def test_extraction_configs(self):
        assert "E0" in EXTRACTION_CONFIGS
        assert "E1" in EXTRACTION_CONFIGS
        assert "E2" in EXTRACTION_CONFIGS
        assert "E3" in EXTRACTION_CONFIGS
        assert "E4" in EXTRACTION_CONFIGS
        assert "E5" in EXTRACTION_CONFIGS

    def test_get_extractor(self):
        extractor = get_extractor("E1", ocr_backend="mock", text_parser_backend="mock")
        assert extractor.config.name == "E1"

    def _create_test_image(self) -> Image.Image:
        """Create a simple test image."""
        return Image.new("RGB", (100, 100), color="white")

    def test_e0_extraction(self):
        extractor = get_extractor("E0", ocr_backend="mock", vlm_backend="mock", text_parser_backend="mock")
        image = self._create_test_image()
        result = extractor.extract(image)
        assert result.config_name == "E0"

    def test_e1_extraction(self):
        # Create mock OCR tokens
        _mock_tokens = [
            OCRToken(text="INV001", bbox=BoundingBox(x=0, y=0, width=50, height=20), confidence=0.9),
            OCRToken(text="Test Vendor", bbox=BoundingBox(x=60, y=0, width=100, height=20), confidence=0.85),
        ]

        extractor = get_extractor("E1", ocr_backend="mock", text_parser_backend="mock")
        # Mock the text parser to return a result
        extractor.text_parser = MockTextParser(
            mock_result=ExtractionResult(
                document_path="test.pdf",
                config_name="E1",
                vendor_name=ExtractedField(
                    field_type=FieldType.VENDOR_NAME,
                    value="Test Vendor",
                    confidence=0.8,
                    evidence=EvidenceSpan(source=ExtractionSource.TEXT_PARSER),
                    source=ExtractionSource.TEXT_PARSER,
                ),
            )
        )

        image = self._create_test_image()
        result = extractor.extract(image)
        assert result.config_name == "E1"


class TestRunAllValidators:
    """Test running all validators."""

    def test_run_all_validators(self):
        result = ExtractionResult(document_path="test.pdf", config_name="E1")
        result.invoice_number = ExtractedField(
            field_type=FieldType.INVOICE_NUMBER,
            value="INV001",
            confidence=0.9,
            evidence=EvidenceSpan(source=ExtractionSource.OCR),
            source=ExtractionSource.OCR,
        )
        result.invoice_date = ExtractedField(
            field_type=FieldType.INVOICE_DATE,
            value="2024-01-15",
            confidence=0.9,
            evidence=EvidenceSpan(source=ExtractionSource.OCR),
            source=ExtractionSource.OCR,
        )

        validations = run_all_validators(result)
        assert len(validations) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
