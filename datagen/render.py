"""PDF rendering with degradations for synthetic invoice generation.

Uses WeasyPrint for HTML to PDF conversion, then applies various degradations
to simulate real-world scans and photos.
"""

import io
import random
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image, ImageDraw, ImageFilter
from PIL.Image import Resampling, Transform

from .models import Invoice, Vendor

# Optional WeasyPrint import - requires system dependencies (GTK/Pango/Cairo)
# Import lazily to avoid hard dependency at module load time
WEASYPRINT_AVAILABLE = None
HTML = None
CSS = None

def _check_weasyprint() -> bool:
    """Check if WeasyPrint is available with all system dependencies."""
    global WEASYPRINT_AVAILABLE, HTML, CSS
    if WEASYPRINT_AVAILABLE is not None:
        return WEASYPRINT_AVAILABLE
    try:
        from weasyprint import CSS as _CSS
        from weasyprint import HTML as _HTML
        HTML = _HTML
        CSS = _CSS
        WEASYPRINT_AVAILABLE = True
    except (ImportError, OSError):
        WEASYPRINT_AVAILABLE = False
        HTML = None
        CSS = None
    return WEASYPRINT_AVAILABLE


class InvoiceRenderer:
    """Renders invoices from templates to PDF with optional degradations."""

    def __init__(self, template_dir: Path, rng: random.Random | None = None):
        self.template_dir = template_dir
        self.rng = rng or random.Random()
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        # Add custom filters
        self.env.filters['indian_format'] = self._indian_format
        self.env.filters['amount_in_words'] = self._amount_in_words
        self.env.filters['amount_in_words_hindi'] = self._amount_in_words_hindi
        self.env.filters['amount_in_words_kannada'] = self._amount_in_words_kannada

    def _indian_format(self, value: Any) -> str:
        """Format number in Indian grouping: 12,34,567.00."""
        try:
            num = float(value)
        except (TypeError, ValueError):
            return str(value)

        # Handle negative
        sign = '-' if num < 0 else ''
        num = abs(num)

        # Split integer and decimal parts
        int_part = int(num)
        dec_part = round(num - int_part, 2)

        # Format integer part with Indian grouping
        s = str(int_part)
        if len(s) <= 3:
            int_formatted = s
        else:
            # Last 3 digits, then groups of 2
            last_three = s[-3:]
            rest = s[:-3]
            groups = []
            while len(rest) > 2:
                groups.insert(0, rest[-2:])
                rest = rest[:-2]
            if rest:
                groups.insert(0, rest)
            int_formatted = ','.join(groups + [last_three])

        # Format decimal part
        dec_str = f"{dec_part:.2f}".split('.')[1]
        return f"{sign}{int_formatted}.{dec_str}"

    def _amount_in_words(self, value: Any) -> str:
        """Convert amount to words in English (Indian numbering)."""
        try:
            num = float(value)
        except (TypeError, ValueError):
            return str(value)

        return self._number_to_words_indian(num)

    def _amount_in_words_hindi(self, value: Any) -> str:
        """Convert amount to words in Hindi."""
        try:
            num = float(value)
        except (TypeError, ValueError):
            return str(value)

        # Simplified - would need proper Hindi number-to-words
        return f"₹{self._indian_format(num)}"

    def _amount_in_words_kannada(self, value: Any) -> str:
        """Convert amount to words in Kannada."""
        try:
            num = float(value)
        except (TypeError, ValueError):
            return str(value)

        # Simplified - would need proper Kannada number-to-words
        return f"₹{self._indian_format(num)}"

    def _number_to_words_indian(self, num: float) -> str:
        """Convert number to words using Indian numbering system."""
        ones = [
            '',
            'One',
            'Two',
            'Three',
            'Four',
            'Five',
            'Six',
            'Seven',
            'Eight',
            'Nine',
        ]
        teens = [
            'Ten',
            'Eleven',
            'Twelve',
            'Thirteen',
            'Fourteen',
            'Fifteen',
            'Sixteen',
            'Seventeen',
            'Eighteen',
            'Nineteen',
        ]
        tens = [
            '',
            '',
            'Twenty',
            'Thirty',
            'Forty',
            'Fifty',
            'Sixty',
            'Seventy',
            'Eighty',
            'Ninety',
        ]

        def convert_hundreds(n: int) -> str:
            if n == 0:
                return ''
            if n < 10:
                return ones[n]
            if n < 20:
                return teens[n - 10]
            if n < 100:
                return tens[n // 10] + (' ' + ones[n % 10] if n % 10 else '')
            return ones[n // 100] + ' Hundred' + (' ' + convert_hundreds(n % 100) if n % 100 else '')

        if num == 0:
            return 'Zero'

        int_part = int(num)
        crore = int_part // 10000000
        lakh = (int_part % 10000000) // 100000
        thousand = (int_part % 100000) // 1000
        hundred = int_part % 1000

        parts = []
        if crore:
            parts.append(convert_hundreds(crore) + ' Crore')
        if lakh:
            parts.append(convert_hundreds(lakh) + ' Lakh')
        if thousand:
            parts.append(convert_hundreds(thousand) + ' Thousand')
        if hundred:
            parts.append(convert_hundreds(hundred))

        result = ' '.join(parts) if parts else 'Zero'
        return result + ' Only'

    def get_template_names(self) -> list[str]:
        """Get list of available template names."""
        templates = []
        for f in self.template_dir.glob("*.html"):
            name = f.stem
            if name.startswith("template_"):
                templates.append(name)
        return sorted(templates)

    def render_html(self, template_name: str, invoice: Invoice, vendor: Vendor) -> str:
        """Render invoice to HTML string."""
        template = self.env.get_template(f"{template_name}.html")
        return template.render(
            invoice=invoice,
            vendor=vendor,
            indian_format=self._indian_format,
            amount_in_words=self._amount_in_words,
            amount_in_words_hindi=self._amount_in_words_hindi,
            amount_in_words_kannada=self._amount_in_words_kannada,
        )

    def render_pdf(self, html_content: str, output_path: Path, keep_text_layer: bool = True) -> None:
        """Render HTML to PDF using WeasyPrint."""
        if not _check_weasyprint():
            raise RuntimeError(
                "WeasyPrint is not available. Please install system dependencies "
                "(GTK/Pango/Cairo) or use Docker. See https://doc.courtbouillon.org/weasyprint/stable/first_steps.html"
            )

        # Create PDF with text layer - HTML is guaranteed to be non-None after _check_weasyprint()
        assert HTML is not None
        html_doc = HTML(string=html_content)
        html_doc.write_pdf(str(output_path))

        # If not keeping text layer, rasterize
        if not keep_text_layer:
            self._rasterize_pdf(output_path)

    def _rasterize_pdf(self, pdf_path: Path, dpi: int = 200) -> None:
        """Convert PDF to images and back to remove text layer."""
        # This would require pdf2image which needs poppler
        # For now, we'll skip full rasterization and just note it
        # In production, use: pdf2image.convert_from_path(pdf_path, dpi=dpi)
        pass

    def apply_degradations(
        self,
        pdf_path: Path,
        output_path: Path | None = None,
        skew_prob: float = 0.5,
        perspective_prob: float = 0.3,
        blur_prob: float = 0.4,
        jpeg_prob: float = 0.5,
        shadow_prob: float = 0.3,
        stamp_prob: float = 0.2,
        handwriting_prob: float = 0.2,
    ) -> Path:
        """Apply random degradations to simulate real-world documents.

        Args:
            pdf_path: Input PDF path
            output_path: Output path (defaults to overwriting input)
            skew_prob: Probability of applying skew/rotation
            perspective_prob: Probability of applying perspective transform
            blur_prob: Probability of applying Gaussian blur
            jpeg_prob: Probability of applying JPEG artifacts
            shadow_prob: Probability of adding shadow overlays
            stamp_prob: Probability of adding stamp overlays
            handwriting_prob: Probability of adding handwriting annotations

        Returns:
            Path to degraded PDF

        """
        if output_path is None:
            output_path = pdf_path

        # For degradations, we need to convert PDF to images first
        # This requires pdf2image and poppler
        # We'll simulate by working with the PDF directly where possible
        # and note that full implementation needs pdf2image

        # For now, copy the file (degradations would be applied after PDF->image conversion)
        import shutil
        shutil.copy2(pdf_path, output_path)

        # TODO: Full implementation with pdf2image:
        # 1. Convert PDF pages to PIL Images
        # 2. Apply each degradation with given probability
        # 3. Save back as PDF

        return output_path

    def _apply_skew(self, img: Image.Image, max_angle: float = 3.0) -> Image.Image:
        """Apply random skew rotation."""
        angle = self.rng.uniform(-max_angle, max_angle)
        return img.rotate(angle, expand=True, fillcolor='white')

    def _apply_perspective(self, img: Image.Image, max_distort: float = 0.02) -> Image.Image:
        """Apply perspective transform to simulate phone photo."""
        width, height = img.size
        # Create perspective transform coefficients
        dx = int(width * max_distort * self.rng.uniform(-1, 1))
        dy = int(height * max_distort * self.rng.uniform(-1, 1))

        # Simple perspective: shift corners
        coords = [
            (0 + dx, 0 + dy),           # top-left
            (width - dx, 0 - dy),       # top-right
            (width + dx, height + dy),  # bottom-right
            (0 - dx, height - dy),      # bottom-left
        ]

        # Use PIL's transform (requires 8 coefficients for quad transform)
        # For simplicity, use affine transform
        return img.transform(
            (width, height),
            Transform.QUAD,
            [c for coord in coords for c in coord],
            Resampling.BICUBIC,
            fillcolor='white'
        )

    def _apply_blur(self, img: Image.Image, max_radius: float = 2.0) -> Image.Image:
        """Apply Gaussian blur."""
        radius = self.rng.uniform(0.5, max_radius)
        return img.filter(ImageFilter.GaussianBlur(radius=radius))

    def _apply_jpeg_artifacts(self, img: Image.Image, min_quality: int = 60, max_quality: int = 85) -> Image.Image:
        """Re-encode as JPEG with artifacts."""
        quality = self.rng.randint(min_quality, max_quality)
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=quality)
        buffer.seek(0)
        return Image.open(buffer)

    def _apply_shadows(self, img: Image.Image) -> Image.Image:
        """Add shadow overlay."""
        width, height = img.size
        shadow = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(shadow)

        # Add a few random shadows
        for _ in range(self.rng.randint(1, 3)):
            x1 = self.rng.randint(0, width // 2)
            y1 = self.rng.randint(0, height // 2)
            x2 = self.rng.randint(width // 2, width)
            y2 = self.rng.randint(height // 2, height)
            opacity = self.rng.randint(20, 60)
            draw.rectangle([x1, y1, x2, y2], fill=(0, 0, 0, opacity))

        # Blur the shadow
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=10))

        # Composite
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        return Image.alpha_composite(img, shadow).convert('RGB')

    def _apply_stamp(self, img: Image.Image, stamp_dir: Path | None = None) -> Image.Image:
        """Overlay a stamp image."""
        # Create a simple stamp programmatically
        width, height = img.size
        stamp_size = min(width, height) // 4

        stamp = Image.new('RGBA', (stamp_size, stamp_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(stamp)

        # Draw a circular stamp
        margin = 10
        draw.ellipse([margin, margin, stamp_size - margin, stamp_size - margin],
                     outline=(200, 0, 0, 200), width=3)
        draw.text((stamp_size // 4, stamp_size // 2 - 10), "PAID", fill=(200, 0, 0, 200))
        draw.text((stamp_size // 4, stamp_size // 2 + 10), "STAMP", fill=(200, 0, 0, 200))

        # Rotate stamp randomly
        stamp = stamp.rotate(self.rng.uniform(-30, 30), expand=True)

        # Paste at random position
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        x = self.rng.randint(0, width - stamp.width)
        y = self.rng.randint(0, height - stamp.height)
        img.paste(stamp, (x, y), stamp)
        return img.convert('RGB')

    def _apply_handwriting(self, img: Image.Image) -> Image.Image:
        """Add handwriting-like annotations."""
        draw = ImageDraw.Draw(img)
        width, height = img.size

        # Add a few random lines/squiggles
        for _ in range(self.rng.randint(1, 5)):
            x1 = self.rng.randint(0, width)
            y1 = self.rng.randint(0, height)
            x2 = self.rng.randint(0, width)
            y2 = self.rng.randint(0, height)
            color = (self.rng.randint(0, 100), self.rng.randint(0, 100), self.rng.randint(0, 100), 180)
            width_line = self.rng.randint(1, 3)
            draw.line([x1, y1, x2, y2], fill=color, width=width_line)

        # Add some text-like marks
        for _ in range(self.rng.randint(0, 3)):
            x = self.rng.randint(50, width - 100)
            y = self.rng.randint(50, height - 50)
            text = self.rng.choice(['✓', '✗', 'OK', '✔', '☐', '☑'])
            draw.text((x, y), text, fill=(0, 100, 0, 200))

        return img


def render_invoice(
    template_name: str,
    invoice: Invoice,
    vendor: Vendor,
    output_path: Path,
    template_dir: Path,
    degrade: bool = True,
    keep_text_layer: bool = True,
    rng: random.Random | None = None,
) -> Path:
    """High-level function to render an invoice to PDF with optional degradations.

    Args:
        template_name: Name of template (without .html)
        invoice: Invoice object
        vendor: Vendor object
        output_path: Output PDF path
        template_dir: Directory containing templates
        degrade: Whether to apply degradations
        keep_text_layer: Whether to keep PDF text layer (50% default)
        rng: Random number generator for reproducibility

    Returns:
        Path to generated PDF

    """
    renderer = InvoiceRenderer(template_dir, rng)

    # Render HTML
    html_content = renderer.render_html(template_name, invoice, vendor)

    # If WeasyPrint not available, write HTML instead for testing
    if not _check_weasyprint():
        output_path = output_path.with_suffix('.html')
        output_path.write_text(html_content, encoding='utf-8')
        return output_path

    # Render PDF with text layer
    renderer.render_pdf(html_content, output_path, keep_text_layer=keep_text_layer)

    # Apply degradations if requested
    if degrade:
        # Decide whether to keep text layer (50% chance)
        if not keep_text_layer or (rng and rng.random() < 0.5):
            # Would need pdf2image for full degradation pipeline
            # For now, skip actual degradation application
            pass

    return output_path


if __name__ == "__main__":
    # Quick test
    import random
    from pathlib import Path

    template_dir = Path(__file__).parent / "templates"
    renderer = InvoiceRenderer(template_dir, random.Random(42))

