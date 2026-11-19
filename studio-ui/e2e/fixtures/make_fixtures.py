"""Regenerate the synthetic E2E fixtures:  python studio-ui/e2e/fixtures/make_fixtures.py"""

from pathlib import Path

import docx
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

HERE = Path(__file__).parent

d = docx.Document()
d.sections[0].header.paragraphs[0].text = "Lakeview Family Health Team (synthetic)"
d.add_paragraph("REFERRAL LETTER - SYNTHETIC EXAMPLE")
d.add_paragraph("Patient: Eleanor Whitfield")
d.add_paragraph("DOB: 1957-04-23")
d.add_paragraph("Phone: (416) 555-0142")
d.add_paragraph("Please assess for persistent cough.")
d.save(HERE / "referral.docx")

c = canvas.Canvas(str(HERE / "lab-report.pdf"), pagesize=letter)
for i, line in enumerate(["LAB REPORT - SYNTHETIC", "Patient: Eleanor Whitfield", "MRN: 00482913"]):
    c.drawString(72, 700 - 18 * i, line)
c.showPage()
c.save()

c = canvas.Canvas(str(HERE / "scanned.pdf"), pagesize=letter)
c.rect(72, 300, 400, 400, fill=1)  # an image-like page with no text layer
c.showPage()
c.save()
