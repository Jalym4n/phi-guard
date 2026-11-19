"""Batch mode: many files in, a ZIP of redacted files plus summary.csv out."""

from __future__ import annotations

import secrets
import threading
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from starlette.datastructures import UploadFile

from phi_guard.batch import BatchItem, process_file, write_zip

from ..context import Studio, get_studio
from ..security import safe_relative_path
from ..state import BatchJob

router = APIRouter()


@router.post("/batch")
async def start_batch(request: Request, studio: Studio = Depends(get_studio)) -> dict[str, Any]:
    s = studio.settings.get()
    max_bytes = s.batch_max_mb * 1024 * 1024
    if int(request.headers.get("content-length") or 0) > max_bytes + 1024 * 1024:
        raise HTTPException(413, f"These files add up to more than the {s.batch_max_mb} MB limit for one batch.")
    form = await request.form(max_files=s.batch_max_files, max_fields=10, max_part_size=1024 * 1024)
    uploads = [u for u in form.getlist("files") if isinstance(u, UploadFile)]
    mode = str(form.get("mode")) if form.get("mode") in ("pseudonymize", "mask") else "mask"
    if not uploads:
        raise HTTPException(400, "Please choose at least one file.")
    if len(uploads) > s.batch_max_files:
        raise HTTPException(413, f"Please choose at most {s.batch_max_files} files at a time.")
    files: list[tuple[str, bytes]] = []
    total = 0
    for u in uploads:
        data = await u.read()
        await u.close()
        total += len(data)
        if total > max_bytes:
            raise HTTPException(413, f"These files add up to more than the {s.batch_max_mb} MB limit for one batch.")
        files.append((safe_relative_path(u.filename or "unnamed.txt"), data))

    job = BatchJob(id=secrets.token_urlsafe(12), total=len(files))
    studio.session.jobs[job.id] = job
    options = {"kinds": s.enabled_kinds, "dictionary": s.dictionary(), "ner": s.ner_enabled and studio.ner_available}
    redactor = studio.session.redactor

    def work() -> None:
        try:
            per_file_limit = s.max_upload_mb * 1024 * 1024
            for i, (name, data) in enumerate(files):
                if len(data) > per_file_limit:
                    job.items.append(BatchItem(name, "skipped", f"Larger than the {s.max_upload_mb} MB limit"))
                else:
                    job.items.append(process_file(name, data, redactor, mode=mode, **options))  # type: ignore[arg-type]
                files[i] = (name, b"")  # drop the original from memory as soon as it is done
            job.zip_bytes = write_zip(job.items)
            job.status = "done"
            counts: dict[str, int] = {}
            for it in job.items:
                for k, n in it.counts.items():
                    counts[k] = counts.get(k, 0) + n
            studio.audit_event(
                "batch",
                files=len(job.items),
                done=sum(it.status == "done" for it in job.items),
                errors=sum(it.status == "error" for it in job.items),
                counts=counts,
                verdicts=sorted({it.verdict for it in job.items if it.verdict}),
            )
        except Exception:  # pragma: no cover - defensive; reported to the UI without details
            job.status = "error"

    threading.Thread(target=work, daemon=True).start()
    return {"id": job.id, "total": job.total}


def _job(studio: Studio, job_id: str) -> BatchJob:
    job = studio.session.jobs.get(job_id)
    if job is None:
        raise HTTPException(
            404, "This batch is no longer available. Batches are cleared when Studio is idle or closed."
        )
    return job


@router.get("/batch/{job_id}")
def batch_status(job_id: str, studio: Studio = Depends(get_studio)) -> dict[str, Any]:
    return _job(studio, job_id).to_dict()


@router.get("/batch/{job_id}/download")
def batch_download(job_id: str, studio: Studio = Depends(get_studio)) -> Response:
    job = _job(studio, job_id)
    if job.status != "done":
        raise HTTPException(409, "This batch is still running.")
    return Response(
        job.zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="phi-guard-redacted.zip"'},
    )
