"""Security controls for the local web server.

Studio is a web server on the user's own computer, which makes it reachable
by *any website the user visits*: a malicious page can tell the browser to
send requests to ``http://127.0.0.1:PORT``.  The controls here stop that:

* **Host header check** (DNS rebinding): an attacker's domain can be made to
  resolve to 127.0.0.1, but the browser still sends ``Host: attacker.example``.
  Only ``127.0.0.1``, ``localhost`` and ``[::1]`` (with our port) are accepted.
* **Per-launch session token** (CSRF): every ``/api`` request must carry the
  random token in the ``X-PHI-Guard-Token`` header.  Other sites cannot read
  it, and a custom header also forces a CORS preflight that we never approve.
* **Origin check**: if the browser sends an ``Origin``, it must be our own.
* **Security headers** on every response: a strict Content Security Policy
  (no inline script, no external origins), ``nosniff``, ``no-referrer``,
  ``DENY`` framing, same-origin opener policy, and ``no-store`` caching for
  API responses so patient details are not written to the browser cache.
"""

from __future__ import annotations

import ipaddress
import secrets
from collections.abc import Awaitable, Callable, Iterable

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

__all__ = [
    "CSP",
    "SECURITY_HEADERS",
    "TOKEN_HEADER",
    "SecurityMiddleware",
    "is_loopback_host",
    "safe_relative_path",
]

TOKEN_HEADER = "X-PHI-Guard-Token"

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
    "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
    "frame-ancestors 'none'; form-action 'self'"
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), interest-cohort=()",
}

_LOCAL_NAMES = ("127.0.0.1", "localhost", "[::1]")


def is_loopback_host(host: str) -> bool:
    """True for addresses that only this computer can reach."""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def _allowed_hosts(port: int, extra: Iterable[str]) -> set[str]:
    names = [*_LOCAL_NAMES, *extra]
    return {n.lower() for n in names} | {f"{n}:{port}".lower() for n in names}


def safe_relative_path(name: str) -> str:
    """Turn an uploaded file name (possibly with folders) into a safe relative path.

    Removes drive letters, absolute paths and ``..`` segments so a crafted
    name cannot write outside the output folder when the ZIP is extracted
    (the "zip slip" attack).
    """
    parts = []
    for part in name.replace("\\", "/").split("/"):
        part = part.strip()
        if part in ("", ".", "..") or (len(part) == 2 and part[1] == ":"):
            continue
        parts.append("".join(ch for ch in part if ch.isprintable() and ch not in '<>:"|?*'))
    cleaned = "/".join(p for p in parts if p)
    return cleaned or "unnamed.txt"


class SecurityMiddleware:
    """Pure ASGI middleware (so it also guards streaming and static responses)."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        token: str,
        port_getter: Callable[[], int],
        extra_hosts: Iterable[str] = (),
        on_activity: Callable[[str], None] | None = None,
    ) -> None:
        self.app = app
        self.token = token
        self.port_getter = port_getter
        self.extra_hosts = tuple(extra_hosts)
        self.on_activity = on_activity

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        path = scope.get("path", "")
        is_api = path.startswith("/api")

        error = self._check(request, is_api)
        if error is not None:
            await self._with_headers(error, is_api)(scope, receive, send)
            return
        if is_api and self.on_activity is not None:
            self.on_activity(path)

        async def send_wrapper(message: dict[str, object]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))  # type: ignore[call-overload]
                existing = {k.decode().lower() for k, _ in headers}
                for k, v in self._headers(is_api).items():
                    if k.lower() not in existing:
                        headers.append((k.encode(), v.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)  # type: ignore[arg-type]

    def _check(self, request: Request, is_api: bool) -> Response | None:
        port = self.port_getter()
        host = request.headers.get("host", "").lower()
        if host not in _allowed_hosts(port, self.extra_hosts):
            return JSONResponse({"error": "This address is not allowed."}, status_code=403)
        origin = request.headers.get("origin")
        if origin is not None and origin.lower() not in {f"http://{h}" for h in _allowed_hosts(port, self.extra_hosts)}:
            return JSONResponse({"error": "Requests from other websites are not allowed."}, status_code=403)
        if is_api:
            sent = request.headers.get(TOKEN_HEADER, "")
            if not secrets.compare_digest(sent.encode(), self.token.encode()):
                return JSONResponse(
                    {"error": "Your Studio session has expired. Please reopen Studio from its desktop shortcut."},
                    status_code=403,
                )
        return None

    @staticmethod
    def _headers(is_api: bool) -> dict[str, str]:
        headers = dict(SECURITY_HEADERS)
        if is_api:
            headers["Cache-Control"] = "no-store"
            headers["Pragma"] = "no-cache"
        return headers

    def _with_headers(self, response: Response, is_api: bool) -> Callable[[Scope, Receive, Send], Awaitable[None]]:
        for k, v in self._headers(is_api).items():
            response.headers[k] = v
        return response
