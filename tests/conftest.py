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
