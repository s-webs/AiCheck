"""Generate official PDF reports with header and stamp."""

import logging
import platform
import tempfile
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, SimpleDocTemplate, Spacer
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)

# Font paths for Cyrillic support
FONT_PATHS = [
    ("Windows", "C:/Windows/Fonts/arial.ttf"),
    ("Windows alt", "C:/Windows/Fonts/DejaVuSans.ttf"),
    ("Darwin", "/System/Library/Fonts/Supplemental/Arial.ttf"),
    ("Linux", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ("Linux alt", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
]

CYRILLIC_FONT_NAME = "CyrillicFont"


def _register_cyrillic_font() -> bool:
    """Register a Cyrillic-capable font. Returns True if successful."""
    for _name, path in FONT_PATHS:
        if Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont(CYRILLIC_FONT_NAME, path))
                return True
            except Exception as e:
                logger.debug("Could not load font %s: %s", path, e)
    logger.warning("No Cyrillic font found; PDF may show replacement chars for RU/KK")
    return False


def _get_assets_path() -> Path:
    """Get path to assets folder."""
    return Path(__file__).resolve().parent.parent / "assets"


def _process_header_image(header_path: Path) -> Path:
    """
    Process header PNG to make black/dark background transparent.
    Returns path to processed image (may be original if processing fails).
    """
    try:
        img = Image.open(header_path).convert("RGBA")
        data = img.getdata()
        
        new_data = []
        for item in data:
            # If pixel is black or very dark (RGB all < 30), make it transparent
            r, g, b, a = item
            if r < 30 and g < 30 and b < 30:
                new_data.append((r, g, b, 0))  # Transparent
            else:
                new_data.append(item)
        
        img.putdata(new_data)
        
        # Save to temporary file
        temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        temp_path = Path(temp_file.name)
        img.save(temp_path, "PNG")
        temp_file.close()
        
        logger.info("Processed header image: made black background transparent")
        return temp_path
    except Exception as e:
        logger.warning("Failed to process header image for transparency: %s", e)
        return header_path


def generate_pdf(
    report_text: str,
    output_path: str | Path,
    header_path: str | Path | None = None,
    stamp_path: str | Path | None = None,
) -> None:
    """
    Generate PDF with header (kolontitul) and stamp.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    assets = _get_assets_path()
    header_path = Path(header_path or assets / "header_kolontitul.jpg")
    stamp_path = Path(stamp_path or assets / "stamp_test.jpg")

    if not header_path.exists():
        logger.warning("Header image not found: %s", header_path)
    if not stamp_path.exists():
        logger.warning("Stamp image not found: %s", stamp_path)

    # Process header image to make black background transparent
    processed_header_path = header_path
    if header_path.exists():
        processed_header_path = _process_header_image(header_path)

    font_ok = _register_cyrillic_font()

    page_width, page_height = A4
    margin = 2 * cm
    header_height = 1.5 * cm
    content_height = page_height - 2 * margin - header_height

    # Track last page number
    last_page = [1]  # Use list to allow modification in closure

    def on_page(canvas, doc):
        canvas.saveState()
        # Update last page number
        last_page[0] = max(last_page[0], doc.page)
        
        # Header image at top - full width with margins
        if processed_header_path.exists():
            img_w = page_width - 2 * margin  # Full width minus margins
            img_h = header_height * 0.8
            canvas.drawImage(
                str(processed_header_path),
                margin,
                page_height - margin - img_h,
                width=img_w,
                height=img_h,
                preserveAspectRatio=True,
            )
        canvas.restoreState()

    doc = BaseDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin + header_height,
        bottomMargin=margin,
    )

    frame = Frame(
        doc.leftMargin,
        doc.bottomMargin,
        doc.width,
        doc.height,
        id="normal",
    )
    template = PageTemplate(id="main", frames=frame, onPage=on_page)
    doc.addPageTemplates([template])

    styles = getSampleStyleSheet()
    body_kw = {
        "name": "CyrillicBody",
        "fontSize": 10,
        "leading": 14,
        "alignment": TA_JUSTIFY,
    }
    if font_ok:
        body_kw["fontName"] = CYRILLIC_FONT_NAME
    body_style = ParagraphStyle(parent=styles["Normal"], **body_kw)

    story = []
    for para in report_text.split("\n\n"):
        para = para.strip()
        if not para:
            story.append(Spacer(1, 0.3 * cm))
            continue
        # Escape XML special chars for ReportLab; preserve line breaks
        para = para.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        para = para.replace("\n", "<br/>")
        try:
            story.append(Paragraph(para, body_style))
        except Exception:
            story.append(Paragraph(para.replace("'", "&#39;"), body_style))
        story.append(Spacer(1, 0.2 * cm))

    doc.build(story)
    
    # Add stamp on last page using pypdf
    if stamp_path.exists() and last_page[0] > 0:
        try:
            from reportlab.pdfgen import canvas as reportlab_canvas
            from io import BytesIO
            
            # Create stamp overlay
            stamp_buffer = BytesIO()
            stamp_canvas = reportlab_canvas.Canvas(stamp_buffer, pagesize=A4)
            stamp_w = 2.5 * cm
            stamp_h = 2.5 * cm
            stamp_canvas.drawImage(
                str(stamp_path),
                page_width - margin - stamp_w,  # Right edge minus margin
                margin,  # Bottom margin
                width=stamp_w,
                height=stamp_h,
                preserveAspectRatio=True,
            )
            stamp_canvas.save()
            stamp_buffer.seek(0)
            
            # Merge stamp overlay with last page
            reader = PdfReader(str(output_path))
            writer = PdfWriter()
            stamp_reader = PdfReader(stamp_buffer)
            
            # Copy all pages except last
            for i in range(len(reader.pages) - 1):
                writer.add_page(reader.pages[i])
            
            # Merge stamp with last page
            last_page_obj = reader.pages[-1]
            stamp_page = stamp_reader.pages[0]
            last_page_obj.merge_page(stamp_page)
            writer.add_page(last_page_obj)
            
            # Write updated PDF
            with open(output_path, 'wb') as output_file:
                writer.write(output_file)
                
            logger.info("Added stamp to last page (%d)", last_page[0])
        except Exception as e:
            logger.warning("Failed to add stamp to last page: %s", e)
    
    # Clean up temporary processed header file if it was created
    if processed_header_path != header_path and processed_header_path.exists():
        try:
            processed_header_path.unlink()
        except Exception as e:
            logger.debug("Could not delete temporary header file: %s", e)
