"""OCR of scanned PDFs and fax images.  All documents are synthetic.

Tests that need the Tesseract program skip when it isn't installed; CI installs it.
"""

from __future__ import annotations

import io
import os
import subprocess
import tempfile

import pytest

pytest.importorskip("PIL")
pytest.importorskip("pypdfium2")

from phi_guard import ocr
from phi_guard.batch import run_batch
from phi_guard.cli import main
from phi_guard.detectors import scan
from phi_guard.documents import (
    DocumentError,
    ScannedPdfError,
    UnsupportedDocument,
    extract_text,
    redacted_scan_pdf,
)
from phi_guard.redactor import Redactor

from .conftest import SCAN_NOTE, make_fax_tiff, make_image, make_mixed_pdf, make_scan_pdf

needs_tesseract = pytest.mark.skipif(not ocr.is_available(), reason="Tesseract is not installed")


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


# --- reading -----------------------------------------------------------------------


@needs_tesseract
def test_scanned_pdf_is_read_and_details_found():
    doc = extract_text(make_scan_pdf(level="fax"), "referral.pdf")
    assert doc.kind == "pdf" and doc.used_ocr and doc.ocr_pages == [1]
    assert doc.ocr is not None and 0.5 < (doc.ocr_confidence or 0) <= 1
    assert any("read from a scanned image" in w for w in doc.warnings)
    kinds = {f.kind for f in scan(doc.text)}
    assert {"PATIENT_NAME", "OHIP_NUMBER", "PHONE", "DATE_OF_BIRTH"} <= kinds


@needs_tesseract
def test_word_offsets_line_up_with_text():
    doc = extract_text(make_scan_pdf(pages=2), "two-pages.pdf")
    assert doc.pages == 2 and doc.ocr_pages == [1, 2]
    assert {w.page for w in doc.ocr.words} == {0, 1}
    for w in doc.ocr.words:
        assert doc.text[w.start : w.end] == w.text


@needs_tesseract
def test_multipage_fax_tiff_at_fax_resolution():
    doc = extract_text(make_fax_tiff([SCAN_NOTE, "Page two: Clara Whitfield, daughter."]), "incoming-fax.tif")
    assert doc.kind == "image" and doc.pages == 2 and doc.ocr_pages == [1, 2]
    assert "Whitfield" in doc.text and "daughter" in doc.text


@needs_tesseract
@pytest.mark.parametrize("fmt,name", [("PNG", "photo.png"), ("JPEG", "photo.jpg")])
def test_png_and_jpeg(fmt, name):
    doc = extract_text(make_image(fmt=fmt), name)
    assert doc.kind == "image" and "Eleanor Whitfield" in doc.text


@needs_tesseract
def test_mixed_pdf_reads_only_the_scanned_page():
    doc = extract_text(make_mixed_pdf(), "fax-with-cover.pdf")
    assert doc.pages == 2 and doc.ocr_pages == [2]
    assert "FAX COVER SHEET" in doc.text and "Whitfield" in doc.text
    assert doc.ocr is None  # not fully scanned, so no redacted-scan copy
    with pytest.raises(DocumentError, match="fully scanned"):
        redacted_scan_pdf(doc, [])


@needs_tesseract
def test_redacted_scan_hides_details_and_has_no_text_layer():
    from pypdf import PdfReader

    doc = extract_text(make_scan_pdf(level="scan"), "referral.pdf")
    spans = [(f.start, f.end) for f in scan(doc.text)]
    pdf = redacted_scan_pdf(doc, spans)
    assert pdf.startswith(b"%PDF-")
    assert all(not (p.extract_text() or "").strip() for p in PdfReader(io.BytesIO(pdf)).pages)
    reread = extract_text(pdf, "redacted.pdf").text
    for secret in ("Whitfield", "5271", "555-0142", "1957"):
        assert _norm(secret) not in _norm(reread)
    assert "persistent cough" in reread  # the rest of the page survives


@needs_tesseract
def test_ocr_never_writes_temporary_files(monkeypatch, tmp_path):
    """Scanned referrals stay in memory, in Python and in the Tesseract process."""
    created: list[str] = []
    for name in ("mkstemp", "NamedTemporaryFile", "TemporaryFile", "mkdtemp", "SpooledTemporaryFile"):
        real = getattr(tempfile, name)
        monkeypatch.setattr(tempfile, name, lambda *a, _r=real, _n=name, **k: created.append(_n) or _r(*a, **k))
    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir()
    for var in ("TMPDIR", "TEMP", "TMP"):
        monkeypatch.setenv(var, str(tmpdir))
    extract_text(make_scan_pdf(), "a.pdf")
    extract_text(make_fax_tiff([SCAN_NOTE]), "b.tif")
    assert created == [] and list(tmpdir.iterdir()) == []


@needs_tesseract
def test_french_language_option():
    langs = ocr.tesseract_info()["languages"]
    if "fra" not in langs:
        pytest.skip("French data not installed")
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if not os.path.exists(font):
        pytest.skip("DejaVu Sans font (with French accents) not installed")
    image = make_image("Patiente : Hélène Côté\nDossier transféré à l'hôpital", font=font)
    assert "Hélène Côté" in extract_text(image, "fr.png", ocr_lang="eng+fra").text


# --- safety limits and errors --------------------------------------------------------


def test_image_too_large_is_refused(monkeypatch):
    monkeypatch.setattr(ocr, "MAX_PAGE_PIXELS", 10_000)
    with pytest.raises(ocr.OcrError, match="too large"):
        ocr.load_images(make_image())


def test_too_many_pages_is_refused(monkeypatch):
    monkeypatch.setattr(ocr, "MAX_OCR_PAGES", 1)
    with pytest.raises(ocr.OcrError, match="split"):
        ocr.load_images(make_fax_tiff(["one", "two"]))
    with pytest.raises(ocr.OcrError):
        ocr.pdf_page_images(make_scan_pdf(pages=2), [0, 1])


def test_damaged_files():
    with pytest.raises(ocr.OcrError, match="damaged"):
        ocr.load_images(b"\x89PNG\r\n\x1a\nnot really")
    with pytest.raises(ocr.OcrError, match="damaged"):
        ocr.pdf_page_images(b"%PDF-1.4 broken", [0])


def test_without_tesseract_the_message_is_friendly(monkeypatch):
    monkeypatch.setattr(ocr, "find_tesseract", lambda: None)
    assert ocr.tesseract_info() == {"available": False, "version": None, "languages": [], "path": None}
    with pytest.raises(ScannedPdfError, match="text-recognition add-on"):
        extract_text(make_image(), "fax.png")
    with pytest.raises(ocr.OcrUnavailable):
        ocr.ocr_images([])


def test_ocr_can_be_turned_off():
    with pytest.raises(UnsupportedDocument, match="turned off"):
        extract_text(make_image(), "fax.png", ocr=False)


def test_invalid_language_rejected(monkeypatch):
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "/bin/true")
    with pytest.raises(ValueError, match="language"):
        ocr.ocr_images([], lang="eng; rm -rf /")


def test_tesseract_failures_become_plain_errors(monkeypatch):
    from PIL import Image

    img = Image.new("L", (50, 50), 255)
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "/usr/bin/tesseract")

    def timeout(*a, **k):
        raise subprocess.TimeoutExpired("tesseract", 1)

    monkeypatch.setattr(ocr.subprocess, "run", timeout)
    with pytest.raises(ocr.OcrError, match="too long"):
        ocr.ocr_images([img])

    monkeypatch.setattr(ocr.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, b"", b"boom"))
    with pytest.raises(ocr.OcrError, match="couldn't read"):
        ocr.ocr_images([img])

    def missing(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(ocr.subprocess, "run", missing)
    with pytest.raises(ocr.OcrUnavailable):
        ocr.ocr_images([img])


def test_find_tesseract_env_override(monkeypatch, tmp_path):
    fake = tmp_path / "tesseract"
    fake.write_text("#!/bin/sh\necho 'tesseract 9.9.9'\necho 'List of available languages (2):'\necho eng\necho osd\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PHI_GUARD_TESSERACT", str(fake))
    assert ocr.find_tesseract() == str(fake)
    if os.name == "posix":
        info = ocr.tesseract_info()
        assert info["version"] == "9.9.9" and info["languages"] == ["eng"]


def test_parse_tsv_layout_and_offsets():
    header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
    rows = [
        "5\t1\t1\t1\t1\t1\t10\t10\t50\t20\t96\tPatient:",
        "5\t1\t1\t1\t1\t2\t70\t10\t60\t20\t91\tEleanor",
        "5\t1\t1\t1\t2\t1\t10\t40\t40\t20\t40\tDOB:",
        "4\t1\t1\t1\t2\t0\t10\t40\t40\t20\t-1\t",
        "5\t1\t2\t1\t1\t1\t10\t90\t40\t20\t-1\t ",
        "5\t1\t2\t1\t1\t2\t10\t90\t40\t20\tbad\tEnd",
    ]
    text, words = ocr._parse_tsv(header + "\n".join(rows), page=0, base=5)
    assert text == "Patient: Eleanor\nDOB:\n\nEnd"
    assert [(w.text, w.start - 5) for w in words] == [("Patient:", 0), ("Eleanor", 9), ("DOB:", 17), ("End", 23)]
    assert words[1].box == (70, 10, 130, 30)
    result = ocr.OcrResult(text, words)
    assert result.low_confidence_words == 1 and result.confidence == pytest.approx((96 + 91 + 40) / 3 / 100, 0.01)
    assert ocr.OcrResult("").confidence is None


def test_images_to_pdf_needs_pages():
    with pytest.raises(ValueError):
        ocr.images_to_pdf([])


# --- batch and command line ----------------------------------------------------------


@needs_tesseract
def test_batch_redacts_scans_and_returns_redacted_scan_copies():
    items = run_batch(
        [("faxes/referral.pdf", make_scan_pdf()), ("faxes/incoming.tiff", make_fax_tiff([SCAN_NOTE]))],
        Redactor(mode="mask"),
    )
    assert [it.status for it in items] == ["done", "done"]
    for it in items:
        assert it.read_from_scan and it.ocr_confidence
        assert b"Whitfield" not in it.output and it.output_name.endswith(".txt")
        ((name, pdf),) = it.extra_outputs.items()
        assert name.endswith(".redacted-scan.pdf") and pdf.startswith(b"%PDF-")
    assert items[1].to_dict()["extra_outputs"] == ["faxes/incoming.redacted-scan.pdf"]


@needs_tesseract
def test_cli_reads_fax_and_reports_status(tmp_path, capsys, monkeypatch):
    fax = tmp_path / "fax.tif"
    fax.write_bytes(make_fax_tiff([SCAN_NOTE]))
    assert main(["scan", str(fax)]) == 0
    captured = capsys.readouterr()
    assert "PATIENT_NAME" in captured.out and "scanned image" in captured.err
    assert main(["ocr-status"]) == 0
    assert "OCR ready" in capsys.readouterr().out
    folder, out = tmp_path / "in", tmp_path / "out"
    folder.mkdir()
    (folder / "r.pdf").write_bytes(make_scan_pdf())
    assert main(["batch", str(folder), "--out", str(out)]) == 0
    assert (out / "r.txt").exists() and (out / "r.redacted-scan.pdf").exists()
    assert "read_from_scan" in (out / "summary.csv").read_text()
    monkeypatch.setattr(ocr, "find_tesseract", lambda: None)
    assert main(["ocr-status"]) == 1
    with pytest.raises(SystemExit, match="add-on"):
        main(["scan", str(fax)])
