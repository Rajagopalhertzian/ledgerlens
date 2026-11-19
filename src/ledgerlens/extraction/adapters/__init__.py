"""OCR, VLM, and text parser adapters."""

from .ocr import MockOCR, OCRBackend, PaddleOCRBackend, TesseractOCR, get_ocr_backend
from .text_parser import MockTextParser, OpenAITextParser, TextParserBackend, get_text_parser
from .vlm import MockVLM, OpenAIVLM, VLMBackend, get_vlm_backend

__all__ = [
    "OCRBackend",
    "TesseractOCR",
    "PaddleOCRBackend",
    "MockOCR",
    "get_ocr_backend",
    "VLMBackend",
    "OpenAIVLM",
    "MockVLM",
    "get_vlm_backend",
    "TextParserBackend",
    "OpenAITextParser",
    "MockTextParser",
    "get_text_parser",
]
