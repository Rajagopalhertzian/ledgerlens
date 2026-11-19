"""Text parser adapter for cheap LLM parsing of OCR text."""

import json
import os
from abc import ABC, abstractmethod
from typing import Any

from ledgerlens.extraction.models import (
    EvidenceSpan,
    ExtractedField,
    ExtractionResult,
    ExtractionSource,
    FieldType,
    LineItem,
    OCRToken,
)


class TextParserBackend(ABC):
    """Abstract base class for text parser backends."""

    @abstractmethod
    def parse(self, ocr_text: str, ocr_tokens: list[OCRToken], schema: dict[str, Any]) -> ExtractionResult:
        """Parse OCR text into structured extraction result."""
        pass

    @abstractmethod
    def estimate_cost(self, text_length: int) -> float:
        """Estimate cost in USD for parsing this text."""
        pass


class OpenAITextParser(TextParserBackend):
    """OpenAI-compatible cheap LLM for text parsing."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ):
        self.model = model
        self.api_key = api_key or os.getenv("CHEAP_MODEL_API_KEY") or os.getenv("LLM_API_KEY")
        self.base_url = base_url or os.getenv("CHEAP_MODEL_BASE_URL")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = None

    def _get_client(self):
        """Lazy load OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as err:
                raise RuntimeError("openai package not installed. Install with: pip install openai") from err

            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def parse(self, ocr_text: str, ocr_tokens: list[OCRToken], schema: dict[str, Any]) -> ExtractionResult:
        """Parse OCR text using cheap LLM with JSON schema."""
        client = self._get_client()

        prompt = self._get_default_prompt()

        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Extract invoice data from this OCR text:\n\n{ocr_text}"},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            response_format={"type": "json_schema", "json_schema": {"name": "invoice_extraction", "schema": schema}},
        )

        content = response.choices[0].message.content
        if content is None:
            return ExtractionResult(document_path="ocr_text", config_name="E1", full_text="", ocr_tokens=ocr_tokens)
        data = json.loads(content)

        return self._parse_output(data, ocr_tokens)

    def _get_default_prompt(self) -> str:
        return """You are an expert at extracting structured data from OCR text of Indian GST invoices.
The text may contain OCR errors. Extract all fields accurately.
For numeric values, preserve the exact format as shown in the text.
For dates, use YYYY-MM-DD format. For GSTIN, use the exact 15-character format.
Return only valid JSON matching the provided schema."""

    def _parse_output(self, data: dict[str, Any], ocr_tokens: list[OCRToken]) -> ExtractionResult:
        """Parse LLM JSON output into ExtractionResult."""
        result = ExtractionResult(
            document_path="ocr_text",
            config_name="E1",  # OCR + cheap LLM
            full_text=" ".join(t.text for t in ocr_tokens),
            ocr_tokens=ocr_tokens,
        )

        field_mapping = {
            "vendor_name": FieldType.VENDOR_NAME,
            "vendor_gstin": FieldType.VENDOR_GSTIN,
            "invoice_number": FieldType.INVOICE_NUMBER,
            "invoice_date": FieldType.INVOICE_DATE,
            "buyer_gstin": FieldType.BUYER_GSTIN,
            "buyer_name": FieldType.BUYER_NAME,
            "po_reference": FieldType.PO_REFERENCE,
            "grn_reference": FieldType.GRN_REFERENCE,
            "subtotal": FieldType.SUBTOTAL,
            "total_tax": FieldType.TOTAL_TAX,
            "grand_total": FieldType.GRAND_TOTAL,
            "currency": FieldType.CURRENCY,
            "place_of_supply": FieldType.PLACE_OF_SUPPLY,
            "place_of_delivery": FieldType.PLACE_OF_DELIVERY,
            "irn": FieldType.IRN,
            "eway_bill_number": FieldType.EWAY_BILL_NUMBER,
            "payment_terms": FieldType.PAYMENT_TERMS,
            "bank_account": FieldType.BANK_ACCOUNT,
            "ifsc": FieldType.IFSC,
        }

        for key, field_type in field_mapping.items():
            if key in data and data[key] is not None:
                value = str(data[key])
                # Find evidence in OCR tokens
                evidence = self._find_evidence_in_tokens(value, ocr_tokens)
                setattr(
                    result,
                    key,
                    ExtractedField(
                        field_type=field_type,
                        value=value,
                        normalized_value=value,
                        confidence=0.8,  # Text parser default confidence
                        evidence=evidence,
                        source=ExtractionSource.TEXT_PARSER,
                        grounded=evidence.is_grounded(),
                    ),
                )

        # Parse line items
        if "line_items" in data and isinstance(data["line_items"], list):
            for idx, item in enumerate(data["line_items"]):
                line_item = self._parse_line_item(item, idx + 1, ocr_tokens)
                if line_item:
                    result.line_items.append(line_item)

        return result

    def _find_evidence_in_tokens(self, value: str, tokens: list[OCRToken]) -> EvidenceSpan:
        """Find OCR tokens that match the extracted value."""
        normalized_value = value.strip().lower()
        matching_indices = []

        for i, token in enumerate(tokens):
            if token.normalized_text() in normalized_value or normalized_value in token.normalized_text():
                matching_indices.append(i)

        if matching_indices:
            bboxes = [tokens[i].bbox for i in matching_indices]
            return EvidenceSpan(
                source=ExtractionSource.TEXT_PARSER, token_indices=matching_indices, bboxes=bboxes, raw_text=value
            )

        return EvidenceSpan(source=ExtractionSource.TEXT_PARSER, raw_text=value)

    def _parse_line_item(self, item: dict[str, Any], line_number: int, ocr_tokens: list[OCRToken]) -> LineItem | None:
        """Parse a single line item."""
        line = LineItem(line_number=line_number)

        field_mapping = {
            "item_code": FieldType.ITEM_CODE,
            "item_description": FieldType.ITEM_DESCRIPTION,
            "hsn_code": FieldType.HSN_CODE,
            "uom": FieldType.UOM,
            "quantity": FieldType.QUANTITY,
            "unit_price": FieldType.UNIT_PRICE,
            "tax_rate": FieldType.TAX_RATE,
            "tax_type": FieldType.TAX_TYPE,
            "discount_percent": FieldType.DISCOUNT_PERCENT,
            "taxable_value": FieldType.TAXABLE_VALUE,
            "tax_amount": FieldType.TAX_AMOUNT,
            "line_total": FieldType.LINE_TOTAL,
        }

        for key, field_type in field_mapping.items():
            if key in item and item[key] is not None:
                value = str(item[key])
                evidence = self._find_evidence_in_tokens(value, ocr_tokens)
                setattr(
                    line,
                    key,
                    ExtractedField(
                        field_type=field_type,
                        value=value,
                        normalized_value=value,
                        confidence=0.8,
                        evidence=evidence,
                        source=ExtractionSource.TEXT_PARSER,
                        grounded=evidence.is_grounded(),
                    ),
                )

        return line

    def estimate_cost(self, text_length: int) -> float:
        """Estimate cost for gpt-4o-mini."""
        # ~$0.15 per 1M input tokens, ~$0.60 per 1M output tokens
        # Rough estimate: 1 token ~= 4 chars
        input_tokens = text_length / 4
        output_tokens = 500  # estimated
        return (input_tokens * 0.15 + output_tokens * 0.60) / 1_000_000


class MockTextParser(TextParserBackend):
    """Mock text parser for testing."""

    def __init__(self, mock_result: ExtractionResult | None = None):
        self.mock_result = mock_result

    def parse(self, ocr_text: str, ocr_tokens: list[OCRToken], schema: dict[str, Any]) -> ExtractionResult:
        if self.mock_result:
            return self.mock_result
        return ExtractionResult(document_path="ocr_text", config_name="E1", full_text=ocr_text, ocr_tokens=ocr_tokens)

    def estimate_cost(self, text_length: int) -> float:
        return 0.0


def get_text_parser(name: str = "openai", **kwargs) -> TextParserBackend:
    """Get text parser backend by name."""
    backends = {"openai": OpenAITextParser, "mock": MockTextParser}
    if name not in backends:
        raise ValueError(f"Unknown text parser: {name}. Available: {list(backends.keys())}")
    return backends[name](**kwargs)
