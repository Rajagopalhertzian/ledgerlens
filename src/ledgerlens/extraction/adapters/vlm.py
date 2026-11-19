"""VLM adapter for vision-language models with JSON schema output."""

import base64
import io
import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from PIL import Image

from ledgerlens.extraction.models import (
    EvidenceSpan,
    ExtractedField,
    ExtractionResult,
    ExtractionSource,
    FieldType,
    LineItem,
)


class VLMBackend(ABC):
    """Abstract base class for VLM backends."""

    @abstractmethod
    def extract(self, image: Image.Image | Path, schema: dict[str, Any], prompt: str | None = None) -> ExtractionResult:
        """Extract structured data from image using VLM."""
        pass

    @abstractmethod
    def estimate_cost(self, image: Image.Image | Path) -> float:
        """Estimate cost in USD for this extraction."""
        pass


class OpenAIVLM(VLMBackend):
    """OpenAI-compatible VLM backend (GPT-4o, GPT-4V, etc.)."""

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ):
        self.model = model
        self.api_key = api_key or os.getenv("VLM_API_KEY") or os.getenv("LLM_API_KEY")
        self.base_url = base_url or os.getenv("VLM_BASE_URL")
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

    def _image_to_base64(self, image: Image.Image | Path) -> str:
        """Convert image to base64 data URL."""
        if isinstance(image, Path):
            with open(image, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        else:
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def extract(self, image: Image.Image | Path, schema: dict[str, Any], prompt: str | None = None) -> ExtractionResult:
        """Extract structured data using VLM with JSON schema."""
        client = self._get_client()

        # Default prompt for invoice extraction
        if prompt is None:
            prompt = self._get_default_prompt()

        # Encode image
        image_b64 = self._image_to_base64(image)

        # Call VLM with structured output
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract all invoice fields from this image."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                    ],
                },
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            response_format={"type": "json_schema", "json_schema": {"name": "invoice_extraction", "schema": schema}},
        )

        # Parse response
        content = response.choices[0].message.content
        if content is None:
            return ExtractionResult(document_path=str(image) if isinstance(image, Path) else "image", config_name="E2")
        data = json.loads(content)

        # Convert to ExtractionResult
        return self._parse_vlm_output(data, image)

    def _get_default_prompt(self) -> str:
        return """You are an expert at extracting structured data from Indian GST invoices.
Extract all fields accurately. For numeric values, preserve the exact format as shown.
For dates, use YYYY-MM-DD format. For GSTIN, use the exact 15-character format.
Return only valid JSON matching the provided schema."""

    def _parse_vlm_output(self, data: dict[str, Any], image: Image.Image | Path) -> ExtractionResult:
        """Parse VLM JSON output into ExtractionResult."""
        result = ExtractionResult(
            document_path=str(image) if isinstance(image, Path) else "image",
            config_name="E2",  # VLM only
        )

        # Map VLM output fields to our model
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
                setattr(
                    result,
                    key,
                    ExtractedField(
                        field_type=field_type,
                        value=value,
                        normalized_value=value,
                        confidence=0.9,  # VLM default confidence
                        evidence=EvidenceSpan(source=ExtractionSource.VLM, raw_text=value),
                        source=ExtractionSource.VLM,
                    ),
                )

        # Parse line items
        if "line_items" in data and isinstance(data["line_items"], list):
            for idx, item in enumerate(data["line_items"]):
                line_item = self._parse_line_item(item, idx + 1)
                if line_item:
                    result.line_items.append(line_item)

        return result

    def _parse_line_item(self, item: dict[str, Any], line_number: int) -> LineItem | None:
        """Parse a single line item from VLM output."""
        line = LineItem(line_number=line_number)

        field_mapping = {
            "item_code": "item_code",
            "item_description": "item_description",
            "hsn_code": "hsn_code",
            "uom": "uom",
            "quantity": "quantity",
            "unit_price": "unit_price",
            "tax_rate": "tax_rate",
            "tax_type": "tax_type",
            "discount_percent": "discount_percent",
            "taxable_value": "taxable_value",
            "tax_amount": "tax_amount",
            "line_total": "line_total",
        }

        for key, attr in field_mapping.items():
            if key in item and item[key] is not None:
                value = str(item[key])
                field_type = getattr(FieldType, key.upper(), None)
                if field_type:
                    setattr(
                        line,
                        attr,
                        ExtractedField(
                            field_type=field_type,
                            value=value,
                            normalized_value=value,
                            confidence=0.9,
                            evidence=EvidenceSpan(source=ExtractionSource.VLM, raw_text=value),
                            source=ExtractionSource.VLM,
                        ),
                    )

        return line

    def estimate_cost(self, image: Image.Image | Path) -> float:
        """Estimate cost based on image size and model pricing."""
        # Rough estimates for GPT-4o (as of 2024)
        # $5.00 per 1M input tokens, $15.00 per 1M output tokens
        # An invoice image ~ 1000-2000 tokens input, ~500 tokens output
        return 0.01  # ~1 cent per invoice


class MockVLM(VLMBackend):
    """Mock VLM for testing."""

    def __init__(self, mock_result: ExtractionResult | None = None):
        self.mock_result = mock_result

    def extract(self, image: Image.Image | Path, schema: dict[str, Any], prompt: str | None = None) -> ExtractionResult:
        if self.mock_result:
            return self.mock_result
        return ExtractionResult(document_path=str(image), config_name="E2")

    def estimate_cost(self, image: Image.Image | Path) -> float:
        return 0.0


def get_vlm_backend(name: str = "openai", **kwargs) -> VLMBackend:
    """Get VLM backend by name."""
    backends = {"openai": OpenAIVLM, "mock": MockVLM}
    if name not in backends:
        raise ValueError(f"Unknown VLM backend: {name}. Available: {list(backends.keys())}")
    return backends[name](**kwargs)
