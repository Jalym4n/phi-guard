"""Studio and scanned documents: OCR on upload, previews, redacted scan download, batch."""

from __future__ import annotations

import base64
import io
import json
import time
import zipfile

import pytest

from phi_guard import ocr

from ..conftest import SCAN_NOTE, make_fax_tiff, make_mixed_pdf, make_scan_pdf

needs_tesseract = pytest.mark.skipif(not ocr.is_available(), reason="Tesseract is not installed")


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def test_health_and_settings_report_ocr(client, monkeypatch):
    h = client.get("/api/health").json()["ocr"]
    assert set(h) == {"available", "version", "languages"}
    s = client.get("/api/settings").json()
    assert s["settings"]["ocr_enabled"] is True and s["settings"]["ocr_language"] == "eng"
    assert s["ocr"]["available"] == h["available"]
    monkeypatch.setattr(ocr, "find_tesseract", lambda: None)
    assert client.get("/api/health").json()["ocr"]["available"] is False


@needs_tesseract
def test_extract_scanned_pdf_reports_ocr_and_previews(client, data_dir):
    r = client.post("/api/extract", files={"file": ("Whitfield_referral.pdf", make_scan_pdf())})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "Eleanor Whitfield" in body["text"]
    assert body["ocr"]["used"] and body["ocr"]["full_scan"] and body["ocr"]["pages"] == [1]
    assert 0.5 < body["ocr"]["confidence"] <= 1
    assert len(body["previews"]) == 1 and body["previews"][0].startswith("data:image/jpeg;base64,")
    assert base64.b64decode(body["previews"][0].split(",", 1)[1])[:3] == b"\xff\xd8\xff"
    entry = client.get("/api/audit", params={"action": "open_file"}).json()["entries"][0]
    assert entry["ocr_pages"] == 1 and "Whitfield" not in json.dumps(entry)
    assert "Whitfield" not in (data_dir / "audit.jsonl").read_text()


@needs_tesseract
def test_extract_fax_tiff_and_mixed_pdf(client):
    tif = client.post("/api/extract", files={"file": ("fax.tif", make_fax_tiff([SCAN_NOTE, "Page two."]))}).json()
    assert tif["kind"] == "image" and tif["pages"] == 2 and len(tif["previews"]) == 2
    mixed = client.post("/api/extract", files={"file": ("cover+fax.pdf", make_mixed_pdf())}).json()
    assert mixed["ocr"]["pages"] == [2] and mixed["ocr"]["full_scan"] is False and mixed["previews"] == []


@needs_tesseract
def test_redacted_scan_download_honours_decisions(client):
    data = make_scan_pdf(level="scan")
    text = client.post("/api/extract", files={"file": ("r.pdf", data)}).json()["text"]
    findings = client.post("/api/scan", json={"text": text}).json()["findings"]
    phone = next(f for f in findings if f["kind"] == "PHONE")
    options = {"mode": "mask", "keep": [{"start": phone["start"], "end": phone["end"]}]}
    r = client.post("/api/redact/scan", files={"file": ("r.pdf", data)}, data={"options": json.dumps(options)})
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    reread = client.post("/api/extract", files={"file": ("out.pdf", r.content)}).json()["text"]
    assert _norm("Whitfield") not in _norm(reread) and _norm("5271") not in _norm(reread)
    assert _norm("555-0142") in _norm(reread)  # kept at the user's request
    entry = client.get("/api/audit", params={"action": "redact"}).json()["entries"][0]
    assert entry["output"] == "scan"


@needs_tesseract
def test_redacted_scan_refused_for_non_scans(client):
    r = client.post("/api/redact/scan", files={"file": ("n.txt", b"Patient: Eleanor Whitfield")})
    assert r.status_code == 422 and "fully scanned" in r.json()["error"]
    bad = client.post("/api/redact/scan", files={"file": ("r.pdf", make_scan_pdf())}, data={"options": "{oops"})
    assert bad.status_code == 422


def test_ocr_turned_off_in_settings(client):
    settings = client.get("/api/settings").json()["settings"]
    settings["ocr_enabled"] = False
    client.put("/api/settings", json=settings)
    r = client.post("/api/extract", files={"file": ("r.pdf", make_scan_pdf())})
    assert r.status_code == 422 and "turned off" in r.json()["error"]


def test_scans_without_tesseract_get_a_friendly_message(client, monkeypatch):
    monkeypatch.setattr(ocr, "find_tesseract", lambda: None)
    r = client.post("/api/extract", files={"file": ("fax.tif", make_fax_tiff([SCAN_NOTE]))})
    assert r.status_code == 422 and "text-recognition add-on" in r.json()["error"]


@needs_tesseract
def test_french_setting_falls_back_when_not_installed(client, monkeypatch):
    settings = client.get("/api/settings").json()["settings"]
    settings["ocr_language"] = "eng+fra"
    assert client.put("/api/settings", json=settings).status_code == 200
    real = ocr.tesseract_info
    monkeypatch.setattr(ocr, "tesseract_info", lambda: {**real(), "languages": ["eng"]})
    r = client.post("/api/extract", files={"file": ("r.pdf", make_scan_pdf())})
    assert r.status_code == 200 and "Whitfield" in r.json()["text"]


@needs_tesseract
def test_batch_with_scans_returns_redacted_scans(client):
    files = [
        ("files", ("faxes/referral.pdf", make_scan_pdf())),
        ("files", ("faxes/incoming.tiff", make_fax_tiff([SCAN_NOTE]))),
    ]
    job = client.post("/api/batch", files=files, data={"mode": "mask"}).json()
    for _ in range(600):
        st = client.get(f"/api/batch/{job['id']}").json()
        if st["status"] != "running":
            break
        time.sleep(0.05)
    assert st["status"] == "done"
    assert all(it["read_from_scan"] for it in st["items"])
    z = client.get(f"/api/batch/{job['id']}/download").content
    with zipfile.ZipFile(io.BytesIO(z)) as zf:
        names = set(zf.namelist())
        assert {"redacted/faxes/referral.txt", "redacted/faxes/referral.redacted-scan.pdf",
                "redacted/faxes/incoming.txt", "redacted/faxes/incoming.redacted-scan.pdf"} <= names  # fmt: skip
        assert "Whitfield" not in zf.read("redacted/faxes/referral.txt").decode()
        assert "yes" in zf.read("summary.csv").decode()
