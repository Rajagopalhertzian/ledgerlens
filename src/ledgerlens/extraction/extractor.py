"""Main extractor with cascade routing (E0-E4 configs)."""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from .adapters.ocr import get_ocr_backend
from .adapters.text_parser import get_text_parser
from .adapters.vlm import get_vlm_backend
from .calibration import ConfidenceCalibrator, calibrate_extraction_result
from .models import ExtractionResult, ExtractionSource, FieldType, OCRToken
from .validators import DeterministicValidators, GroundingValidator, run_all_validators


@dataclass
class ExtractionConfig:
    """Configuration for extraction pipeline."""

    name: str  # E0, E1, E2, E3, E4, E5

    # Backend settings
    ocr_backend: str = "tesseract"
    vlm_backend: str = "openai"
    text_parser_backend: str = "openai"

    # Cascade thresholds
    confidence_threshold: float = 0.7  # Below this, escalate to VLM
    field_confidence_threshold: float = 0.6  # Per-field threshold

    # Cost control
    max_cost_usd: float = 0.10  # Max cost per document
    max_latency_ms: float = 30000  # Max latency per document

    # Calibration
    calibrator: ConfidenceCalibrator | None = None

    # Validation
    run_validators: bool = True
    run_grounding: bool = True


# Default configs for ablation
EXTRACTION_CONFIGS = {
    "E0": ExtractionConfig(
        name="E0",
        ocr_backend="tesseract",
        vlm_backend="mock",
        text_parser_backend="mock",
        run_validators=True,
        run_grounding=False,
    ),
    "E1": ExtractionConfig(
        name="E1",
        ocr_backend="tesseract",
        vlm_backend="mock",
        text_parser_backend="openai",
        run_validators=True,
        run_grounding=True,
    ),
    "E2": ExtractionConfig(
        name="E2",
        ocr_backend="tesseract",
        vlm_backend="openai",
        text_parser_backend="mock",
        run_validators=True,
        run_grounding=True,
    ),
    "E3": ExtractionConfig(
        name="E3",
        ocr_backend="tesseract",
        vlm_backend="openai",
        text_parser_backend="openai",
        run_validators=True,
        run_grounding=True,
    ),
    "E4": ExtractionConfig(
        name="E4",
        ocr_backend="tesseract",
        vlm_backend="openai",
        text_parser_backend="openai",
        confidence_threshold=0.7,
        field_confidence_threshold=0.6,
        run_validators=True,
        run_grounding=True,
    ),
    "E5": ExtractionConfig(
        name="E5",
        ocr_backend="tesseract",
        vlm_backend="openai",
        text_parser_backend="openai",
        confidence_threshold=0.7,
        field_confidence_threshold=0.6,
        run_validators=True,
        run_grounding=True,
    ),
}


class Extractor:
    """Main extraction pipeline with cascade routing."""

    def __init__(self, config: ExtractionConfig):
        self.config = config
        self.ocr = get_ocr_backend(config.ocr_backend)
        self.vlm = get_vlm_backend(config.vlm_backend)
        self.text_parser = get_text_parser(config.text_parser_backend)
        self.grounding_validator = GroundingValidator()
        self.deterministic_validators = DeterministicValidators()

        # JSON schema for structured output
        self.schema = self._build_schema()

    def _build_schema(self) -> dict[str, Any]:
        """Build JSON schema for structured extraction."""
        return {
            "type": "object",
            "properties": {
                "vendor_name": {"type": "string"},
                "vendor_gstin": {
                    "type": "string",
                    "pattern": "^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[A-Z0-9]{1}[A-Z0-9]{1}$",
                },
                "invoice_number": {"type": "string"},
                "invoice_date": {"type": "string", "format": "date"},
                "buyer_gstin": {
                    "type": "string",
                    "pattern": "^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[A-Z0-9]{1}[A-Z0-9]{1}$",
                },
                "buyer_name": {"type": "string"},
                "po_reference": {"type": "string"},
                "grn_reference": {"type": "string"},
                "subtotal": {"type": "string"},
                "total_tax": {"type": "string"},
                "grand_total": {"type": "string"},
                "currency": {"type": "string", "enum": ["INR"]},
                "place_of_supply": {"type": "string"},
                "place_of_delivery": {"type": "string"},
                "irn": {"type": "string"},
                "eway_bill_number": {"type": "string"},
                "payment_terms": {"type": "string"},
                "bank_account": {"type": "string"},
                "ifsc": {"type": "string"},
                "line_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "line_number": {"type": "integer"},
                            "item_code": {"type": "string"},
                            "item_description": {"type": "string"},
                            "hsn_code": {"type": "string"},
                            "uom": {"type": "string"},
                            "quantity": {"type": "string"},
                            "unit_price": {"type": "string"},
                            "tax_rate": {"type": "string"},
                            "tax_type": {"type": "string", "enum": ["CGST", "SGST", "IGST", "CESS"]},
                            "discount_percent": {"type": "string"},
                            "taxable_value": {"type": "string"},
                            "tax_amount": {"type": "string"},
                            "line_total": {"type": "string"},
                        },
                    },
                },
            },
            "required": ["vendor_name", "vendor_gstin", "invoice_number", "invoice_date"],
        }

    def extract(self, document: Image.Image | Path) -> ExtractionResult:
        """Run extraction pipeline based on config."""
        start_time = time.time()
        total_cost = 0.0

        # Load image
        if isinstance(document, Path):
            image = Image.open(document)
            if image.mode != "RGB":
                image = image.convert("RGB")
        else:
            image = document

        # Step 1: OCR (always runs)
        ocr_start = time.time()
        ocr_tokens = self.ocr.extract(image)
        full_text = self.ocr.extract_full_text(image)
        _ = (time.time() - ocr_start) * 1000
        total_cost += 0.0  # Tesseract is free

        # Initialize result
        result = ExtractionResult(
            document_path=str(document) if isinstance(document, Path) else "image",
            config_name=self.config.name,
            full_text=full_text,
            ocr_tokens=ocr_tokens,
            extraction_time_ms=0,
            cost_usd=0,
        )

        # Run pipeline based on config
        if self.config.name == "E0":
            result = self._run_e0(result, image)
        elif self.config.name == "E1":
            result = self._run_e1(result, image, ocr_tokens, full_text)
        elif self.config.name == "E2":
            result = self._run_e2(result, image)
        elif self.config.name == "E3":
            result = self._run_e3(result, image, ocr_tokens, full_text)
        elif self.config.name in ("E4", "E5"):
            result = self._run_e4_e5(result, image, ocr_tokens, full_text)

        # Run validators
        if self.config.run_validators:
            result.validations = run_all_validators(result)

        # Calibrate confidence
        if self.config.calibrator:
            result = calibrate_extraction_result(result, self.config.calibrator)
        else:
            result = calibrate_extraction_result(result)

        # Final metadata
        result.extraction_time_ms = (time.time() - start_time) * 1000
        result.cost_usd = total_cost

        return result

    def _run_e0(self, result: ExtractionResult, image: Image.Image) -> ExtractionResult:
        """E0: OCR + rule/regex parsing (floor)."""
        # Simple regex-based extraction from OCR text
        # This is a placeholder - real implementation would use regex rules
        result.warnings.append("E0: Using basic OCR only, no structured extraction")
        return result

    def _run_e1(
        self, result: ExtractionResult, image: Image.Image, ocr_tokens: list[OCRToken], full_text: str
    ) -> ExtractionResult:
        """E1: OCR + cheap LLM text parse."""
        # Parse with cheap LLM
        parsed = self.text_parser.parse(full_text, ocr_tokens, self.schema)

        # Copy fields to result
        for field_type, field in parsed.get_header_fields().items():
            setattr(result, field_type.value.lower(), field)

        result.line_items = parsed.line_items
        result.warnings.append("E1: OCR + cheap LLM text parse")
        return result

    def _run_e2(self, result: ExtractionResult, image: Image.Image) -> ExtractionResult:
        """E2: Strong VLM only."""
        vlm_result = self.vlm.extract(image, self.schema)

        # Copy fields
        for field_type, field in vlm_result.get_header_fields().items():
            setattr(result, field_type.value.lower(), field)

        result.line_items = vlm_result.line_items
        result.warnings.append("E2: Strong VLM only")
        return result

    def _run_e3(
        self, result: ExtractionResult, image: Image.Image, ocr_tokens: list[OCRToken], full_text: str
    ) -> ExtractionResult:
        """E3: Fused E1 + E2 with grounding, validators, calibrated confidence."""
        # Run both E1 and E2
        e1_result = self.text_parser.parse(full_text, ocr_tokens, self.schema)
        e2_result = self.vlm.extract(image, self.schema)

        # Fuse results
        result = self._fuse_results(e1_result, e2_result, ocr_tokens)
        result.warnings.append("E3: Fused OCR+LLM + VLM with grounding")
        return result

    def _run_e4_e5(
        self, result: ExtractionResult, image: Image.Image, ocr_tokens: list[OCRToken], full_text: str
    ) -> ExtractionResult:
        """E4/E5: Cascade routing - cheap first, escalate low-confidence fields to VLM."""
        # Start with E1 (cheap)
        e1_result = self.text_parser.parse(full_text, ocr_tokens, self.schema)

        # Identify low-confidence fields
        low_conf_fields = self._identify_low_confidence_fields(e1_result)

        if low_conf_fields and self.config.vlm_backend != "mock":
            # Escalate to VLM for low-confidence fields
            vlm_result = self.vlm.extract(image, self.schema)

            # Fuse with VLM overriding low-confidence fields
            result = self._fuse_with_cascade(e1_result, vlm_result, low_conf_fields, ocr_tokens)
            result.warnings.append(f"E{self.config.name[-1]}: Cascade - VLM used for {len(low_conf_fields)} fields")
        else:
            # No VLM or no low-confidence fields
            result = e1_result
            result.config_name = self.config.name
            result.ocr_tokens = ocr_tokens
            result.warnings.append(f"E{self.config.name[-1]}: No cascade needed")

        return result

    def _identify_low_confidence_fields(self, result: ExtractionResult) -> list[FieldType]:
        """Identify fields below confidence threshold."""
        low_conf = []

        for field_type, field in result.get_header_fields().items():
            if field.confidence < self.config.field_confidence_threshold:
                low_conf.append(field_type)

        for item in result.line_items:
            for field in item.get_all_fields():
                if field.confidence < self.config.field_confidence_threshold:
                    low_conf.append(field.field_type)

        return low_conf

    def _fuse_results(
        self, e1_result: ExtractionResult, e2_result: ExtractionResult, ocr_tokens: list[OCRToken]
    ) -> ExtractionResult:
        """Fuse E1 and E2 results with grounding."""
        fused = ExtractionResult(
            document_path=e1_result.document_path,
            config_name="E3",
            full_text=e1_result.full_text,
            ocr_tokens=ocr_tokens,
        )

        # For each field, pick the better grounded result
        all_field_types = set()
        all_field_types.update(e1_result.get_header_fields().keys())
        all_field_types.update(e2_result.get_header_fields().keys())

        for field_type in all_field_types:
            e1_field = e1_result.get_header_fields().get(field_type)
            e2_field = e2_result.get_header_fields().get(field_type)

            if e1_field and e2_field:
                # Prefer grounded field
                if e1_field.grounded and not e2_field.grounded:
                    chosen = e1_field
                elif e2_field.grounded and not e1_field.grounded:
                    chosen = e2_field
                else:
                    # Both grounded or both ungrounded - pick higher confidence
                    chosen = e1_field if e1_field.confidence >= e2_field.confidence else e2_field

                # Mark as fused
                chosen.source = ExtractionSource.FUSED
                setattr(fused, field_type.value.lower(), chosen)

            elif e1_field:
                setattr(fused, field_type.value.lower(), e1_field)
            elif e2_field:
                setattr(fused, field_type.value.lower(), e2_field)

        # Fuse line items (simplified - use E1 line items)
        fused.line_items = e1_result.line_items

        return fused

    def _fuse_with_cascade(
        self,
        e1_result: ExtractionResult,
        vlm_result: ExtractionResult,
        low_conf_fields: list[FieldType],
        ocr_tokens: list[OCRToken],
    ) -> ExtractionResult:
        """Fuse with cascade - VLM overrides low-confidence fields."""
        fused = ExtractionResult(
            document_path=e1_result.document_path,
            config_name=self.config.name,
            full_text=e1_result.full_text,
            ocr_tokens=ocr_tokens,
        )

        low_conf_set = set(low_conf_fields)

        # Header fields
        for field_type in set(e1_result.get_header_fields().keys()) | set(vlm_result.get_header_fields().keys()):
            e1_field = e1_result.get_header_fields().get(field_type)
            vlm_field = vlm_result.get_header_fields().get(field_type)

            if field_type in low_conf_set and vlm_field:
                # Use VLM for low-confidence fields
                vlm_field.source = ExtractionSource.FUSED
                setattr(fused, field_type.value.lower(), vlm_field)
            elif e1_field:
                setattr(fused, field_type.value.lower(), e1_field)
            elif vlm_field:
                setattr(fused, field_type.value.lower(), vlm_field)

        # Line items - use E1 for now
        fused.line_items = e1_result.line_items

        return fused


def get_extractor(config_name: str = "E3", **kwargs) -> Extractor:
    """Get extractor by config name."""
    if config_name not in EXTRACTION_CONFIGS:
        raise ValueError(f"Unknown config: {config_name}. Available: {list(EXTRACTION_CONFIGS.keys())}")
    config = EXTRACTION_CONFIGS[config_name]
    # Override with kwargs
    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)
    return Extractor(config)
