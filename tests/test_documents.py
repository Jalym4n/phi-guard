import io
import zipfile

import pytest

from phi_guard.documents import (
    DocumentError,
    ScannedPdfError,
    UnsupportedDocument,
    detect_kind,
    docx_with_replacements,
    extract_text,
)

from .conftest import make_docx, make_pdf


def test_txt_encodings():
    assert extract_text("héllo".encode()).text == "héllo"
    assert extract_text(b"\xef\xbb\xbfbom").encoding == "utf-8-sig"
    assert extract_text("utf16 ✓".encode("utf-16")).text == "utf16 ✓"
    doc = extract_text("café".encode("cp1252"), "a.txt")
    assert doc.text == "café" and doc.encoding == "cp1252" and doc.warnings


def test_txt_from_path(tmp_path):
    p = tmp_path / "n.txt"
    p.write_text("SIN 123 456 782", encoding="utf-8")
    doc = extract_text(p)
    assert doc.kind == "txt" and "123 456 782" in doc.text


def test_docx_paragraphs_tables_header_in_order():
    data = make_docx(["Patient: Eleanor Whitfield", "Plan: rest"], table=[["DOB", "1957-04-23"]], header="Lakeview")
    doc = extract_text(data, "letter.docx")
    assert doc.kind == "docx"
    assert doc.text.splitlines() == ["Lakeview", "Patient: Eleanor Whitfield", "Plan: rest", "DOB", "1957-04-23"]


def test_docx_with_replacements_spans_and_callable():
    import docx

    data = make_docx(["Patient: Eleanor Whitfield", "Plan: rest"], header="Lakeview")
    text = extract_text(data, "x.docx").text
    s = text.index("Eleanor")
    out = docx_with_replacements(data, [(s, s + len("Eleanor Whitfield"), "[PATIENT_NAME]")])
    assert extract_text(out, "x.docx").text.splitlines()[1] == "Patient: [PATIENT_NAME]"
    # Span crossing a paragraph break: token in first paragraph, rest removed.
    s2 = text.index("Whitfield")
    out2 = docx_with_replacements(data, [(s2, text.index("rest"), "[X]")])
    assert extract_text(out2, "x.docx").text.splitlines()[1:] == ["Patient: Eleanor [X]", "rest"]
    out3 = docx_with_replacements(data, lambda p: p.upper())
    assert docx.Document(io.BytesIO(out3)).paragraphs[0].text == "PATIENT: ELEANOR WHITFIELD"


def test_text_pdf_and_scanned_pdf():
    doc = extract_text(make_pdf(["Patient: Eleanor Whitfield", "SIN 123 456 782"]), "r.pdf")
    assert doc.kind == "pdf" and doc.pages == 1 and "Eleanor Whitfield" in doc.text
    with pytest.raises(ScannedPdfError, match="scanned image"):
        extract_text(make_pdf(None), "scan.pdf")


def test_damaged_pdf_and_docx():
    with pytest.raises(DocumentError):
        extract_text(b"%PDF-1.4 garbage", "x.pdf")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", "not xml")
    with pytest.raises(DocumentError):
        extract_text(buf.getvalue(), "x.docx")


@pytest.mark.parametrize(
    "data,name",
    [
        (b"MZ\x90\x00rest", "notes.txt"),
        (b"\x7fELF\x02", None),
        (b"#!/bin/sh\nrm -rf /", "run.txt"),
        (b"\x1f\x8b\x08\x00", "a.txt"),
        (b"plain", "virus.exe"),
        (b"\x00\x01\x02binary", "x.txt"),
        (b"PK\x03\x04broken", "x.docx"),
    ],
)
def test_rejects_executables_archives_and_binaries(data, name):
    with pytest.raises(UnsupportedDocument):
        detect_kind(data, name)


def test_rejects_plain_zip_and_extension_mismatch():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.txt", "x")
    with pytest.raises(UnsupportedDocument, match="archive"):
        detect_kind(buf.getvalue(), "files.zip".replace(".zip", ".docx"))
    with pytest.raises(UnsupportedDocument, match="look like"):
        detect_kind(b"%PDF-1.7", "report.txt")
