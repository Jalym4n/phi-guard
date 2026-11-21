"""Shared fixtures.  Every value in this test suite is synthetic."""

from __future__ import annotations

import io

import pytest

SAMPLE_NOTE = (
    "Patient: Eleanor Whitfield\n"
    "DOB: 1957-04-23\n"
    "OHIP: 5271-938-465 AB\n"
    "Address: 48 Maple Grove Crescent, Hamilton ON L8S 4K1\n"
    "Phone: (416) 555-0142\n"
)


@pytest.fixture
def sample_note() -> str:
    return SAMPLE_NOTE


def make_docx(paragraphs: list[str], table: list[list[str]] | None = None, header: str | None = None) -> bytes:
    import docx

    d = docx.Document()
    if header is not None:
        d.sections[0].header.paragraphs[0].text = header
    for p in paragraphs:
        para = d.add_paragraph()
        # Split into two runs so run-merging is exercised.
        half = len(p) // 2
        para.add_run(p[:half]).bold = True
        para.add_run(p[half:])
    if table:
        t = d.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, val in enumerate(row):
                t.cell(r, c).text = val
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def make_pdf(lines: list[str] | None) -> bytes:
    """A text PDF, or (lines=None) a PDF with only a drawn shape, like a scan."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    if lines is None:
        c.rect(100, 100, 300, 300, fill=1)
    else:
        y = 700
        for line in lines:
            c.drawString(72, y, line)
            y -= 16
    c.showPage()
    c.save()
    return buf.getvalue()


SCAN_NOTE = (
    "REFERRAL - SYNTHETIC EXAMPLE\n"
    "Patient: Eleanor Whitfield\n"
    "DOB: 1957-04-23\n"
    "Health card: 5271-938-465 AB\n"
    "Phone: (416) 555-0142\n"
    "Please assess for persistent cough.\n"
)


def make_scan_pdf(text: str = SCAN_NOTE, level: str = "fax", pages: int = 1) -> bytes:
    """A PDF whose pages are only pictures of text, like a scanned or faxed referral."""
    from eval.fax import render_page

    images = [render_page(text, level, seed=i).convert("L") for i in range(pages)]
    buf = io.BytesIO()
    images[0].save(buf, "PDF", save_all=True, append_images=images[1:], resolution=200)
    return buf.getvalue()


def make_fax_tiff(texts: list[str]) -> bytes:
    """A multi-page Group 4 TIFF at standard fax resolution (204 x 98 dpi), as fax machines send."""
    from eval.fax import render_page

    frames = []
    for i, t in enumerate(texts):
        img = render_page(t, "fax", seed=i).convert("L")
        frames.append(img.resize((img.width, img.height * 98 // 204)).convert("1"))  # squash like a real fax
    buf = io.BytesIO()
    frames[0].save(buf, "TIFF", save_all=True, append_images=frames[1:], compression="group4", dpi=(204, 98))
    return buf.getvalue()


def make_image(text: str = SCAN_NOTE, fmt: str = "PNG", level: str = "scan", font: str | None = None) -> bytes:
    from eval.fax import render_page

    buf = io.BytesIO()
    render_page(text, level, font=font).convert("L").save(buf, fmt)
    return buf.getvalue()


def make_mixed_pdf() -> bytes:
    """Page 1 has a text layer (typed cover sheet); page 2 is a scanned image."""
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for blob in (make_pdf(["FAX COVER SHEET - SYNTHETIC", "To: Lakeview Clinic"]), make_scan_pdf()):
        for page in PdfReader(io.BytesIO(blob)).pages:
            writer.add_page(page)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()
