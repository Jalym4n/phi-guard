"""Settings and protection-key management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from starlette.datastructures import UploadFile

from ..context import Studio, get_studio
from ..keystore import KeyStoreError, fingerprint
from ..labels import DETECTOR_INFO
from ..settings_store import Settings
from .models import PasswordIn

router = APIRouter()


def _key_status(studio: Studio) -> dict[str, Any]:
    st = studio.keystore.status()
    return {"exists": st.exists, "backend": st.backend, "location": st.location, "fingerprint": st.fingerprint}


@router.get("/settings")
def get_settings(studio: Studio = Depends(get_studio)) -> dict[str, Any]:
    return {
        "settings": studio.settings.get().model_dump(),
        "detectors": [{"kind": k, "label": label, "example": ex} for k, label, ex in DETECTOR_INFO],
        "ner_available": studio.ner_available,
        "audit_path": str(studio.audit.path),
        "key": _key_status(studio),
    }


@router.put("/settings")
def put_settings(new: Settings, studio: Studio = Depends(get_studio)) -> dict[str, Any]:
    saved = studio.settings.update(new)
    studio.session.idle_timeout = saved.idle_timeout_minutes * 60
    studio.audit_event(
        "settings_changed",
        enabled=len(saved.enabled_kinds),
        always_terms=len(saved.always_remove),
        never_terms=len(saved.never_remove),
    )
    return get_settings(studio)


@router.get("/key")
def key_status(studio: Studio = Depends(get_studio)) -> dict[str, Any]:
    return _key_status(studio)


@router.post("/key/rotate")
def rotate_key(studio: Studio = Depends(get_studio)) -> dict[str, Any]:
    key = studio.keystore.rotate()
    studio.session.set_key(key)
    studio.audit_event("key_created", fingerprint=fingerprint(key))
    return _key_status(studio)


@router.post("/key/export")
def export_key(body: PasswordIn, studio: Studio = Depends(get_studio)) -> Response:
    try:
        blob = studio.keystore.export(body.password)
    except KeyStoreError as exc:
        raise HTTPException(422, str(exc)) from exc
    studio.audit_event("key_exported")
    return Response(
        blob,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="phi-guard-key-backup.json"'},
    )


@router.post("/key/import")
async def import_key(request: Request, studio: Studio = Depends(get_studio)) -> dict[str, Any]:
    form = await request.form(max_files=1, max_fields=5, max_part_size=64 * 1024)
    upload, password = form.get("file"), form.get("password")
    if not isinstance(upload, UploadFile) or not isinstance(password, str) or not password:
        raise HTTPException(400, "Please choose a key file and enter its password.")
    data = await upload.read(64 * 1024)
    try:
        key = studio.keystore.import_(data, password)
    except KeyStoreError as exc:
        raise HTTPException(422, str(exc)) from exc
    studio.session.set_key(key)
    studio.audit_event("key_imported", fingerprint=fingerprint(key))
    return _key_status(studio)
