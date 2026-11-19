"""Activity log: list, verify, export, open folder."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from ..context import Studio, get_studio

router = APIRouter()


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(422, "That date isn't valid.") from exc


@router.get("/audit")
def list_audit(
    studio: Studio = Depends(get_studio),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    action: str | None = None,
    verdict: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    t0, t1 = _parse_time(since), _parse_time(until)
    rows = []
    for e in studio.audit.entries():
        if action and e.get("event") != action:
            continue
        if verdict and e.get("verdict") != verdict and verdict not in (e.get("verdicts") or []):
            continue
        ts = datetime.fromisoformat(e["ts"])
        if (t0 and ts < t0) or (t1 and ts > t1):
            continue
        rows.append({k: v for k, v in e.items() if k not in ("hash", "prev_hash")})
    rows.reverse()  # newest first
    start = (page - 1) * page_size
    return {
        "entries": rows[start : start + page_size],
        "total": len(rows),
        "page": page,
        "page_size": page_size,
        "actions": sorted({e.get("event", "") for e in studio.audit.entries()}),
    }


@router.post("/audit/verify")
def verify_audit(studio: Studio = Depends(get_studio)) -> dict[str, Any]:
    ok, broken = studio.audit.verify()
    count = sum(1 for _ in studio.audit.entries()) if ok else None
    return {"ok": ok, "broken_line": broken, "entries": count}


@router.get("/audit/export")
def export_audit(studio: Studio = Depends(get_studio)) -> Response:
    data = studio.audit.path.read_bytes() if studio.audit.path.exists() else b""
    return Response(
        data,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="phi-guard-activity-log.jsonl"'},
    )


@router.post("/audit/open-folder")
def open_folder(studio: Studio = Depends(get_studio)) -> dict[str, Any]:
    folder = studio.audit.path.parent
    folder.mkdir(parents=True, exist_ok=True)
    try:
        if sys.platform.startswith("win"):  # pragma: no cover - platform specific
            os.startfile(folder)  # type: ignore[attr-defined]
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, str(folder)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return {"opened": False, "path": str(folder)}
    return {"opened": True, "path": str(folder)}
