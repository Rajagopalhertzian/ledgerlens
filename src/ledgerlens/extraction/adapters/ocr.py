"""OCR adapters for Tesseract and PaddleOCR."""

import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

from PIL import Image

from ledgerlens.extraction.models import BoundingBox, OCRToken


class OCRBackend(ABC):
    """Abstract base class for OCR backends."""

    @abstractmethod
    def extract(self, image: Image.Image | Path) -> list[OCRToken]:
        """Extract text tokens with bounding boxes and confidences."""
        pass

    @abstractmethod
    def extract_full_text(self, image: Image.Image | Path) -> str:
        """Extract full text as a single string."""
        pass


class TesseractOCR(OCRBackend):
    """Tesseract OCR backend (CPU baseline)."""

    def __init__(
        self,
        lang: str = "eng+hin",  # English + Hindi for bilingual support
        config: str = "--psm 6 --oem 3",
        dpi: int = 300,
    ):
        self.lang = lang
        self.config = config
        self.dpi = dpi

    def _run_tesseract(self, image_path: Path, output_format: str = "tsv") -> str:
        """Run tesseract and return output."""
        with tempfile.NamedTemporaryFile(suffix=f".{output_format}", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            cmd = ["tesseract", str(image_path), str(tmp_path.with_suffix("")), "-l", self.lang, self.config]
            if output_format == "tsv":
                cmd.append("tsv")
            elif output_format == "txt":
                cmd.append("txt")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                raise RuntimeError(f"Tesseract failed: {result.stderr}")

            if output_format == "tsv":
                return tmp_path.read_text()
            else:
                return tmp_path.read_text()
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
            # Also clean up the base file tesseract creates
            base = tmp_path.with_suffix("")
            if base.exists():
                base.unlink()

    def extract(self, image: Image.Image | Path) -> list[OCRToken]:
        """Extract tokens with bounding boxes using Tesseract TSV output."""
        if isinstance(image, Image.Image):
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                image.save(tmp.name, dpi=(self.dpi, self.dpi))
                image_path = Path(tmp.name)
            cleanup = True
        else:
            image_path = image
            cleanup = False

        try:
            tsv_output = self._run_tesseract(image_path, "tsv")
            tokens = self._parse_tsv(tsv_output)
            return tokens
        finally:
            if cleanup and image_path.exists():
                image_path.unlink()

    def _parse_tsv(self, tsv_output: str) -> list[OCRToken]:
        """Parse Tesseract TSV output into OCRToken list."""
        lines = tsv_output.strip().split("\n")
        if len(lines) < 2:
            return []

        headers = lines[0].split("\t")
        tokens = []

        for line in lines[1:]:
            parts = line.split("\t")
            if len(parts) != len(headers):
                continue

            row = dict(zip(headers, parts, strict=False))

            # Skip empty or low confidence
            try:
                conf = float(row.get("conf", -1))
                if conf < 0:
                    continue
                text = row.get("text", "").strip()
                if not text:
                    continue
            except (ValueError, TypeError):
                continue

            try:
                x = int(row.get("left", 0))
                y = int(row.get("top", 0))
                w = int(row.get("width", 0))
                h = int(row.get("height", 0))
                block_num = int(row.get("block_num", 0))
                line_num = int(row.get("line_num", 0))
                word_num = int(row.get("word_num", 0))
            except (ValueError, TypeError):
                continue

            tokens.append(
                OCRToken(
                    text=text,
                    bbox=BoundingBox(x=x, y=y, width=w, height=h),
                    confidence=conf / 100.0,  # Tesseract uses 0-100
                    block_num=block_num,
                    line_num=line_num,
                    word_num=word_num,
                )
            )

        return tokens

    def extract_full_text(self, image: Image.Image | Path) -> str:
        """Extract full text as a single string."""
        if isinstance(image, Image.Image):
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                image.save(tmp.name, dpi=(self.dpi, self.dpi))
                image_path = Path(tmp.name)
            cleanup = True
        else:
            image_path = image
            cleanup = False

        try:
            text = self._run_tesseract(image_path, "txt")
            return text.strip()
        finally:
            if cleanup and image_path.exists():
                image_path.unlink()


class PaddleOCRBackend(OCRBackend):
    """PaddleOCR backend (optional GPU)."""

    def __init__(
        self,
        lang: str = "en",
        use_gpu: bool = False,
        use_angle_cls: bool = True,
        det_model_dir: str | None = None,
        rec_model_dir: str | None = None,
    ):
        self.lang = lang
        self.use_gpu = use_gpu
        self.use_angle_cls = use_angle_cls
        self.det_model_dir = det_model_dir
        self.rec_model_dir = rec_model_dir
        self._ocr = None

    def _get_ocr(self):
        """Lazy load PaddleOCR."""
        if self._ocr is None:
            try:
                from paddleocr import PaddleOCR  # type: ignore[import-not-found]

                self._ocr = PaddleOCR(
                    lang=self.lang,
                    use_gpu=self.use_gpu,
                    use_angle_cls=self.use_angle_cls,
                    det_model_dir=self.det_model_dir,
                    rec_model_dir=self.rec_model_dir,
                    show_log=False,
                )
            except ImportError as err:
                raise RuntimeError("PaddleOCR not installed. Install with: pip install paddleocr") from err
        return self._ocr

    def extract(self, image: Image.Image | Path) -> list[OCRToken]:
        """Extract tokens with bounding boxes using PaddleOCR."""
        ocr = self._get_ocr()

        if isinstance(image, Image.Image):
            # Convert to RGB if needed
            if image.mode != "RGB":
                image = image.convert("RGB")
            # Save to temp file for PaddleOCR
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                image.save(tmp.name)
                image_path = tmp.name
            cleanup = True
        else:
            image_path = str(image)
            cleanup = False

        try:
            result = ocr.ocr(image_path, cls=self.use_angle_cls)
            tokens = self._parse_paddle_result(result)
            return tokens
        finally:
            if cleanup:
                Path(image_path).unlink(missing_ok=True)

    def _parse_paddle_result(self, result: list) -> list[OCRToken]:
        """Parse PaddleOCR result into OCRToken list."""
        tokens = []

        if not result or not result[0]:
            return tokens

        for line in result[0]:
            if not line or len(line) < 2:
                continue

            bbox_points = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            text, conf = line[1]

            if not text or conf < 0:
                continue

            # Convert 4-point bbox to x, y, w, h
            xs = [p[0] for p in bbox_points]
            ys = [p[1] for p in bbox_points]
            x = int(min(xs))
            y = int(min(ys))
            w = int(max(xs) - min(xs))
            h = int(max(ys) - min(ys))

            tokens.append(OCRToken(text=text, bbox=BoundingBox(x=x, y=y, width=w, height=h), confidence=float(conf)))

        return tokens

    def extract_full_text(self, image: Image.Image | Path) -> str:
        """Extract full text as a single string."""
        tokens = self.extract(image)
        return " ".join(t.text for t in tokens)


class MockOCR(OCRBackend):
    """Mock OCR for testing without external dependencies."""

    def __init__(self, mock_tokens: list[OCRToken] | None = None, mock_text: str = ""):
        self.mock_tokens = mock_tokens or []
        self.mock_text = mock_text

    def extract(self, image: Image.Image | Path) -> list[OCRToken]:
        return self.mock_tokens

    def extract_full_text(self, image: Image.Image | Path) -> str:
        return self.mock_text


def get_ocr_backend(name: str = "tesseract", **kwargs) -> OCRBackend:
    """Get OCR backend by name."""
    backends = {"tesseract": TesseractOCR, "paddleocr": PaddleOCRBackend, "mock": MockOCR}
    if name not in backends:
        raise ValueError(f"Unknown OCR backend: {name}. Available: {list(backends.keys())}")
    return backends[name](**kwargs)
