"""Remove patient details, check a document, restore names, check an AI answer."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from starlette.datastructures import UploadFile

from phi_guard.documents import DocumentError, detect_kind, docx_with_replacements, extract_text
from phi_guard.finding import Finding, from_utf16, utf16_index_map
from phi_guard.injection import analyze
from phi_guard.output_scan import scan_output
from phi_guard.redactor import manual_finding

from .. import __version__
from ..context import Studio, get_studio
from ..labels import KIND_LABELS, RULE_EXPLANATIONS, VERDICT_TEXT
from .models import RedactIn, ScanIn, TextIn

router = APIRouter()

NEEDS_CHECK_BELOW = 0.85


# --- helpers -----------------------------------------------------------------


def findings_out(text: str, findings: list[Finding]) -> list[dict[str, Any]]:
    m = utf16_index_map(text)
    return [
        {
            "id": f"{m[f.start]}-{m[f.end]}-{f.kind}",
            "kind": f.kind,
            "label": KIND_LABELS.get(f.kind, f.kind.replace("_", " ").title()),
            "start": m[f.start],
            "end": m[f.end],
            "text": f.text,
            "confidence": f.confidence,
            "needs_check": f.confidence < NEEDS_CHECK_BELOW,
            "source": f.source,
        }
        for f in findings
    ]


def summary(counts: dict[str, int]) -> list[dict[str, Any]]:
    return [{"kind": k, "label": KIND_LABELS.get(k, k), "count": n} for k, n in counts.items()]


def _scan_options(studio: Studio) -> dict[str, Any]:
    s = studio.settings.get()
    return {"dictionary": s.dictionary(), "ner": s.ner_enabled and studio.ner_available}


async def read_upload(request: Request, studio: Studio, field: str = "file") -> tuple[str, bytes, dict[str, str]]:
    """Read one uploaded file fully into memory (never to a temp file)."""
    limit = studio.settings.get().max_upload_mb * 1024 * 1024
    declared = int(request.headers.get("content-length") or 0)
    if declared > limit + 64 * 1024:
        raise HTTPException(413, f"This file is larger than the {limit // (1024 * 1024)} MB limit.")
    form = await request.form(max_files=1, max_fields=10, max_part_size=1024 * 1024)
    upload = form.get(field)
    if not isinstance(upload, UploadFile):
        raise HTTPException(400, "Please choose a file.")
    data = await upload.read()
    await upload.close()
    if len(data) > limit:
        raise HTTPException(413, f"This file is larger than the {limit // (1024 * 1024)} MB limit.")
    fields = {k: v for k, v in form.items() if isinstance(v, str)}
    return upload.filename or "document.txt", data, fields


def _redact(studio: Studio, body: RedactIn) -> tuple[Any, str]:
    text = body.text
    s = studio.settings.get()
    keep = [(from_utf16(text, k.start), from_utf16(text, k.end)) for k in body.keep]
    length16 = utf16_index_map(text)[-1]
    if any(m.end > length16 for m in body.manual):
        raise HTTPException(422, "One of the selections you added is outside the text.")
    try:
        manual = [
            manual_finding(text, from_utf16(text, m.start), from_utf16(text, m.end), m.kind)
            for m in body.manual
            if m.end > m.start
        ]
    except ValueError as exc:
        raise HTTPException(422, "One of the selections you added is outside the text.") from exc
    result = studio.session.redactor.redact(
        text, s.enabled_kinds, keep=keep, manual=manual, mode=body.mode, **_scan_options(studio)
    )
    return result, text


# --- endpoints ---------------------------------------------------------------


@router.get("/health")
def health(studio: Studio = Depends(get_studio)) -> dict[str, Any]:
    status = studio.keystore.status()
    return {
        "status": "ok",
        "version": __version__,
        "ner_available": studio.ner_available,
        "key_backend": status.backend,
    }


@router.get("/session")
def session_info(studio: Studio = Depends(get_studio)) -> dict[str, Any]:
    studio.session.check_idle()
    return {
        "idle_timeout_seconds": studio.session.idle_timeout,
        "seconds_remaining": round(studio.session.seconds_remaining()),
        "codes_in_memory": studio.session.redactor.vault_size,
        "cleared_for_inactivity": studio.session.cleared_for_idle,
    }


@router.post("/session/clear")
def session_clear(studio: Studio = Depends(get_studio)) -> dict[str, Any]:
    studio.session.clear()
    studio.audit_event("start_over")
    return {"ok": True}


@router.post("/scan")
def scan_text(body: ScanIn, studio: Studio = Depends(get_studio)) -> dict[str, Any]:
    from phi_guard.detectors import scan

    s = studio.settings.get()
    kinds = [k for k in (body.kinds or s.enabled_kinds) if k in s.enabled_kinds or body.kinds]
    try:
        found = scan(body.text, kinds, **_scan_options(studio))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    counts: dict[str, int] = {}
    for f in found:
        counts[f.kind] = counts.get(f.kind, 0) + 1
    return {"findings": findings_out(body.text, found), "summary": summary(counts)}


@router.post("/redact")
def redact(body: RedactIn, studio: Studio = Depends(get_studio)) -> dict[str, Any]:
    result, _ = _redact(studio, body)
    counts = result.counts()
    if body.final:
        studio.audit_event(
            "redact",
            mode=body.mode,
            counts=counts,
            kept=len(result.kept),
            manual=len(body.manual),
        )
    return {"text": result.text, "summary": summary(counts), "removed": len(result.findings), "kept": len(result.kept)}


@router.post("/redact/docx")
async def redact_docx(request: Request, studio: Studio = Depends(get_studio)) -> Response:
    """Re-send the original .docx with the same decisions; get a redacted .docx back."""
    name, data, fields = await read_upload(request, studio)
    try:
        if detect_kind(data, name) != "docx":
            raise HTTPException(422, "Word output is only available for .docx files.")
        doc = extract_text(data, name)
        body = RedactIn.model_validate({**json.loads(fields.get("options", "{}")), "text": doc.text, "final": True})
    except DocumentError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, "The redaction options were not valid.") from exc
    result, _ = _redact(studio, body)
    spans = [(f.start, f.end, studio.session.redactor.token_for(f.kind, f.text, body.mode)) for f in result.findings]
    out = docx_with_replacements(data, spans)
    studio.audit_event("redact", mode=body.mode, counts=result.counts(), kept=len(result.kept), output="docx")
    return Response(
        out,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="redacted.docx"'},
    )


@router.post("/extract")
async def extract(request: Request, studio: Studio = Depends(get_studio)) -> dict[str, Any]:
    name, data, _ = await read_upload(request, studio)
    try:
        doc = extract_text(data, name)
    except DocumentError as exc:
        raise HTTPException(422, str(exc)) from exc
    # The file name is deliberately not logged: names like "Smith_J_referral.docx" are patient details.
    studio.audit_event("open_file", kind=doc.kind, size_kb=round(len(data) / 1024))
    return {
        "text": doc.text,
        "kind": doc.kind,
        "pages": doc.pages,
        "warnings": doc.warnings,
        "filename": name,
        "size": len(data),
    }


@router.post("/inject")
def inject(body: TextIn, studio: Studio = Depends(get_studio)) -> dict[str, Any]:
    report = analyze(body.text)
    m = utf16_index_map(body.text)
    findings = []
    for f in report.findings:
        key = "base64" if f.source == "base64" else f.rule
        findings.append(
            {
                "rule": f.rule,
                "source": f.source,
                "explanation": RULE_EXPLANATIONS.get(key, "Looks like an instruction aimed at an AI."),
                "start": m[f.start],
                "end": m[f.end],
                "match": f.match[:300],
            }
        )
    studio.audit_event("check_document", verdict=report.verdict, score=round(report.score, 2), rules=report.rules)
    return {
        "score": round(report.score * 100),
        "verdict": report.verdict,
        **VERDICT_TEXT[report.verdict],
        "findings": findings,
        "hidden_characters": report.hidden_characters,
        "cleaned_text": report.normalized_text,
    }


@router.post("/restore")
def restore(body: TextIn, studio: Studio = Depends(get_studio)) -> dict[str, Any]:
    from phi_guard.redactor import TOKEN_RE

    total = len(TOKEN_RE.findall(body.text))
    text, missing = studio.session.redactor.restore_detailed(body.text)
    restored = len(TOKEN_RE.findall(body.text)) - len(TOKEN_RE.findall(text))
    studio.audit_event("restore", restored=restored, not_available=len(missing))
    return {"text": text, "restored": restored, "codes_found": total, "not_available": missing}


@router.post("/output-scan")
def output_scan(body: TextIn, studio: Studio = Depends(get_studio)) -> dict[str, Any]:
    s = studio.settings.get()
    found = scan_output(body.text, studio.session.redactor.known_tokens, s.enabled_kinds, dictionary=s.dictionary())
    counts: dict[str, int] = {}
    for f in found:
        counts[f.kind] = counts.get(f.kind, 0) + 1
    studio.audit_event("check_ai_answer", counts=counts)
    return {"findings": findings_out(body.text, found), "summary": summary(counts)}
