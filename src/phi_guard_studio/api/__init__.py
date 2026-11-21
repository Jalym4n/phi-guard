"""HTTP API routers.  Everything lives under ``/api`` and requires the session token."""

from fastapi import APIRouter

from . import audit, batch, core, settings

router = APIRouter(prefix="/api")
router.include_router(core.router)
router.include_router(batch.router)
router.include_router(audit.router)
router.include_router(settings.router)

__all__ = ["router"]
