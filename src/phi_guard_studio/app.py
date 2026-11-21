"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.formparsers import MultiPartParser

from phi_guard.audit import AuditLog

from . import __version__
from .api import router
from .config import StudioConfig
from .context import Studio
from .keystore import KeyStore
from .security import SecurityMiddleware
from .settings_store import SettingsStore
from .state import SessionState

__all__ = ["create_app"]

PACKAGED_STATIC = Path(__file__).parent / "static"
#: Polling the countdown must not itself count as activity.
PASSIVE_PATHS = ("/api/session",)

FALLBACK_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>phi-guard Studio</title></head>
<body><main><h1>phi-guard Studio</h1><p>The user interface has not been built. From the repository run
<code>make studio-ui</code>, then restart Studio. The API is running.</p></main></body></html>"""


def create_app(
    config: StudioConfig | None = None,
    *,
    keystore: KeyStore | None = None,
    ner_available: bool | None = None,
) -> FastAPI:
    config = config or StudioConfig()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    settings = SettingsStore(config.settings_path)
    keystore = keystore or KeyStore(config.data_dir)
    s = settings.get()

    # Keep uploads in memory.  Starlette otherwise spools files over 1 MB to a temporary
    # file on disk, which would write patient documents to disk without the user's consent.
    MultiPartParser.spool_max_size = max(s.batch_max_mb, s.max_upload_mb, 500) * 1024 * 1024

    if ner_available is None:
        from phi_guard import ner

        ner_available = ner.is_available()

    studio = Studio(
        config=config,
        settings=settings,
        keystore=keystore,
        session=SessionState(keystore.get_or_create(), idle_timeout=s.idle_timeout_minutes * 60),
        audit=AuditLog(config.audit_path),
        ner_available=ner_available,
        port=config.port,
    )

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async def idle_watch() -> None:
            while True:
                await asyncio.sleep(10)
                studio.session.check_idle()

        task = asyncio.create_task(idle_watch())
        try:
            yield
        finally:
            task.cancel()
            studio.session.clear()  # the vault never outlives the app

    app = FastAPI(
        title="phi-guard Studio",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.studio = studio

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"error": "Something in this request wasn't valid. Please try again."}, status_code=422)

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, exc: Exception) -> JSONResponse:  # pragma: no cover - defensive
        # Never echo exception text: it could contain patient details.
        return JSONResponse({"error": "Something went wrong. Please try again."}, status_code=500)

    app.include_router(router)

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "DELETE"])
    def api_not_found(rest: str) -> Response:
        return JSONResponse({"error": "Not found."}, status_code=404)

    static_dir = config.static_dir or PACKAGED_STATIC
    if (static_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    else:

        @app.get("/", response_class=HTMLResponse)
        def fallback() -> str:
            return FALLBACK_PAGE

    def on_activity(path: str) -> None:
        if path not in PASSIVE_PATHS:
            studio.session.touch()

    app.add_middleware(
        SecurityMiddleware,
        token=config.token,
        port_getter=lambda: studio.port,
        extra_hosts=config.extra_hosts,
        on_activity=on_activity,
    )
    return app
