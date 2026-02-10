"""Generate official PDF reports with header and stamp."""

import logging
import platform
import re
import tempfile
from pathlib import Path

from PIL import Image as PILImage
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Image as PlatypusImage,
)
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY, TA_CENTER
from reportlab.pdfgen import canvas
from io import BytesIO

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
CYRILLIC_FONT_BOLD_NAME = "CyrillicFontBold"


def _register_cyrillic_font() -> bool:
    """Register Cyrillic-capable fonts (regular and bold). Returns True if successful."""
    font_registered = False
    bold_font_registered = False
    
    # Try to register regular font
    for _name, path in FONT_PATHS:
        if Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont(CYRILLIC_FONT_NAME, path))
                font_registered = True
                break
            except Exception as e:
                logger.debug("Could not load font %s: %s", path, e)
    
    # Try to register bold font
    bold_paths = [
        ("Windows", "C:/Windows/Fonts/arialbd.ttf"),
        ("Windows alt", "C:/Windows/Fonts/DejaVuSans-Bold.ttf"),
        ("Darwin", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        ("Linux", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("Linux alt", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ]
    
    for _name, path in bold_paths:
        if Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont(CYRILLIC_FONT_BOLD_NAME, path))
                bold_font_registered = True
                break
            except Exception as e:
                logger.debug("Could not load bold font %s: %s", path, e)
    
    if not font_registered:
        logger.warning("No Cyrillic font found; PDF may show replacement chars for RU/KK")
    elif not bold_font_registered:
        logger.debug("Bold Cyrillic font not found; will use regular font for titles")
    
    return font_registered


def _get_assets_path() -> Path:
    """Get path to assets folder."""
    return Path(__file__).resolve().parent.parent / "assets"


def _convert_markdown_to_reportlab(text: str) -> tuple[str, str | None]:
    """
    Convert markdown-like formatting to ReportLab XML tags.
    - # Heading → bold larger font (returns text and 'heading1' style indicator)
    - ## Heading → bold medium font (returns text and 'heading2' style indicator)
    - **text** → <b>text</b>
    - *text* → <i>text</i>
    
    Returns:
        tuple: (converted_text, style_indicator) where style_indicator is None for normal text,
               'heading1' for # headings, 'heading2' for ## headings
    """
    # First escape XML special chars (but preserve our markdown)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    # Check if entire paragraph is a heading (starts with # at beginning)
    heading_match = re.match(r'^(#+)\s+(.+)$', text.strip())
    style_indicator = None
    if heading_match:
        hashes = heading_match.group(1)
        heading_text = heading_match.group(2)
        
        # Determine heading level
        if len(hashes) == 1:
            style_indicator = 'heading1'
        elif len(hashes) >= 2:
            style_indicator = 'heading2'
        
        # Process markdown formatting inside heading
        text = heading_text
    
    # Convert **bold** to <b>bold</b>
    # Use non-greedy matching to handle multiple bold sections
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    
    # Convert *italic* to <i>italic</i>
    # But avoid matching **bold** (already processed)
    # Match single * that's not part of **
    text = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', r'<i>\1</i>', text)
    
    return (text, style_indicator)


def _process_header_image(header_path: Path) -> Path:
    """
    Process header PNG to make black/dark background transparent.
    Returns path to processed image (may be original if processing fails).
    """
    try:
        img = PILImage.open(header_path).convert("RGBA")
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
    assessment_data: dict | None = None,
    output_stream: BytesIO | None = None,
) -> None:
    """
    Generate PDF with header (kolontitul) and stamp.

    Args:
        report_text: Formatted report text
        output_path: Path to output PDF file (ignored if output_stream is provided)
        header_path: Optional path to header image
        stamp_path: Optional path to stamp image
        assessment_data: Optional assessment data dict for generating charts
        output_stream: If provided, PDF is written here instead of to output_path
    """
    use_temp = output_stream is not None
    if use_temp:
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        actual_output = Path(tmp.name)
        tmp.close()
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        actual_output = output_path

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
    
    # Check if bold font is available
    bold_font_ok = CYRILLIC_FONT_BOLD_NAME in pdfmetrics.getRegisteredFontNames()

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
        str(actual_output),
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
    
    # Create title style (main heading: bold, centered, larger font)
    title_kw = {
        "name": "CyrillicTitle",
        "fontSize": 18,
        "leading": 22,
        "alignment": TA_CENTER,
        "spaceAfter": 0.5 * cm,
    }
    if bold_font_ok:
        title_kw["fontName"] = CYRILLIC_FONT_BOLD_NAME
    elif font_ok:
        title_kw["fontName"] = CYRILLIC_FONT_NAME
    title_style = ParagraphStyle(parent=styles["Normal"], **title_kw)
    
    # Create heading styles for # headings
    heading1_kw = {
        "name": "CyrillicHeading1",
        "fontSize": 14,
        "leading": 18,
        "alignment": TA_CENTER,  # centered headings
        "spaceAfter": 0.4 * cm,
        "spaceBefore": 0.3 * cm,
    }
    if bold_font_ok:
        heading1_kw["fontName"] = CYRILLIC_FONT_BOLD_NAME
    elif font_ok:
        heading1_kw["fontName"] = CYRILLIC_FONT_NAME
    heading1_style = ParagraphStyle(parent=styles["Normal"], **heading1_kw)
    
    heading2_kw = {
        "name": "CyrillicHeading2",
        "fontSize": 12,
        "leading": 16,
        "alignment": TA_CENTER,  # centered sub-headings
        "spaceAfter": 0.3 * cm,
        "spaceBefore": 0.2 * cm,
    }
    if bold_font_ok:
        heading2_kw["fontName"] = CYRILLIC_FONT_BOLD_NAME
    elif font_ok:
        heading2_kw["fontName"] = CYRILLIC_FONT_NAME
    heading2_style = ParagraphStyle(parent=styles["Normal"], **heading2_kw)

    story = []
    paragraphs = report_text.split("\n\n")
    charts_inserted = False
    
    for i, para in enumerate(paragraphs):
        para = para.strip()
        if not para:
            story.append(Spacer(1, 0.3 * cm))
            continue
        
        # Check if this is the title "ЗАКЛЮЧЕНИЕ"
        if i == 0 and para.strip().upper().startswith("ЗАКЛЮЧЕНИЕ"):
            # Convert markdown formatting (but keep as title style)
            para_converted, _ = _convert_markdown_to_reportlab(para)
            para_converted = para_converted.replace("\n", "<br/>")
            try:
                story.append(Paragraph(para_converted, title_style))
            except Exception:
                story.append(Paragraph(para_converted.replace("'", "&#39;"), title_style))
            story.append(Spacer(1, 0.3 * cm))
            continue
        
        # Check if we're at the "АНАЛИТИЧЕСКИЕ ГРАФИКИ" section and insert charts
        if not charts_inserted and assessment_data and "АНАЛИТИЧЕСКИЕ ГРАФИКИ" in para.upper():
            # Convert markdown formatting
            para_converted, style_indicator = _convert_markdown_to_reportlab(para)
            para_converted = para_converted.replace("\n", "<br/>")
            
            # Choose style based on markdown conversion result
            if style_indicator == 'heading1':
                para_style = heading1_style
            elif style_indicator == 'heading2':
                para_style = heading2_style
            else:
                para_style = body_style
            
            try:
                story.append(Paragraph(para_converted, para_style))
            except Exception:
                story.append(Paragraph(para_converted.replace("'", "&#39;"), para_style))
            story.append(Spacer(1, 0.3 * cm))
            
            # Generate and insert charts
            try:
                from .charts import create_quality_scores_chart, create_risk_distribution_chart
                
                quality_scores = assessment_data.get("quality_scores", {})
                risk_level = assessment_data.get("risk_level", "LOW")
                major_findings = assessment_data.get("major_findings", [])
                
                # Create quality scores chart
                chart1_bytes = create_quality_scores_chart(quality_scores)
                chart1_img = PlatypusImage(BytesIO(chart1_bytes), width=16 * cm, height=9 * cm)
                story.append(chart1_img)
                story.append(Spacer(1, 0.5 * cm))
                
                # Create risk distribution chart
                chart2_bytes = create_risk_distribution_chart(risk_level, major_findings)
                chart2_img = PlatypusImage(BytesIO(chart2_bytes), width=14 * cm, height=10 * cm)
                story.append(chart2_img)
                story.append(Spacer(1, 0.3 * cm))
                
                charts_inserted = True
                logger.info("Charts inserted into PDF")
            except Exception as e:
                logger.warning("Failed to insert charts: %s", e)
            continue
        
        # Regular paragraph - convert markdown formatting
        para_converted, style_indicator = _convert_markdown_to_reportlab(para)
        para_converted = para_converted.replace("\n", "<br/>")
        
        # Choose style based on markdown conversion result
        if style_indicator == 'heading1':
            para_style = heading1_style
        elif style_indicator == 'heading2':
            para_style = heading2_style
        else:
            para_style = body_style
        
        try:
            story.append(Paragraph(para_converted, para_style))
        except Exception:
            story.append(Paragraph(para_converted.replace("'", "&#39;"), para_style))
        story.append(Spacer(1, 0.2 * cm))

    doc.build(story)
    
    # Add stamp on last page using pypdf
    if stamp_path.exists() and last_page[0] > 0:
        try:
            from reportlab.pdfgen import canvas as reportlab_canvas
            
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
            reader = PdfReader(str(actual_output))
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
            if output_stream is not None:
                writer.write(output_stream)
                output_stream.seek(0)
            else:
                with open(actual_output, 'wb') as output_file:
                    writer.write(output_file)
                
            logger.info("Added stamp to last page (%d)", last_page[0])
        except Exception as e:
            logger.warning("Failed to add stamp to last page: %s", e)
    elif output_stream is not None:
        # No stamp or stamp failed: write built PDF to stream
        with open(actual_output, 'rb') as f:
            output_stream.write(f.read())
        output_stream.seek(0)
    
    # Clean up temp file when writing to stream
    if use_temp and actual_output.exists():
        try:
            actual_output.unlink()
        except Exception as e:
            logger.debug("Could not delete temporary PDF file: %s", e)
    
    # Clean up temporary processed header file if it was created
    if processed_header_path != header_path and processed_header_path.exists():
        try:
            processed_header_path.unlink()
        except Exception as e:
            logger.debug("Could not delete temporary header file: %s", e)
