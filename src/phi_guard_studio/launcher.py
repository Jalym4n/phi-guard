"""``phi-guard-studio``: start the local server and open the browser.

By default Studio listens on 127.0.0.1 (this computer only) on a random free
port, with a fresh random session token.  The browser is opened at
``http://127.0.0.1:PORT/#token=...``: the part after ``#`` is never sent to
the server or written to any log, and the page removes it from the address
bar as soon as it has read it.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import webbrowser
from collections.abc import Sequence
from pathlib import Path

from .config import DEFAULT_DATA_DIR, StudioConfig
from .security import is_loopback_host

BANNER = r"""
  phi-guard Studio {version}
  Runs only on this computer. Nothing is uploaded.
"""

NETWORK_WARNING = """
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  WARNING: Studio is listening on {host}, not just this computer.
  Other devices on the network may be able to reach it. Patient details pass
  through this app. Only do this inside a container or on a network you
  control, and never on public Wi-Fi.
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="phi-guard-studio", description="Start phi-guard Studio in your browser.")
    p.add_argument("--host", default="127.0.0.1", help="address to listen on (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=0, help="port (default: a random free port)")
    p.add_argument("--allow-network", action="store_true", help="allow listening on a non-local address (unsafe)")
    p.add_argument("--no-browser", action="store_true", help="don't open a browser window")
    p.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="settings and activity log folder")
    return p


def check_host(host: str, allow_network: bool) -> str | None:
    """Return an error message if ``host`` is not allowed, else None."""
    if is_loopback_host(host):
        return None
    if not allow_network:
        return (
            f"Refusing to listen on {host!r}: Studio only listens on this computer (127.0.0.1) unless you pass "
            "--allow-network."
        )
    return None


def bind_socket(host: str, port: int) -> socket.socket:
    family = socket.AF_INET6 if ":" in host.strip("[]") else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host.strip("[]"), port))
    sock.listen(64)
    return sock


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    error = check_host(args.host, args.allow_network)
    if error:
        print(error, file=sys.stderr)
        return 2

    from . import __version__

    print(BANNER.format(version=__version__))
    if not is_loopback_host(args.host):
        print(NETWORK_WARNING.format(host=args.host), file=sys.stderr)

    sock = bind_socket(args.host, args.port)
    port = sock.getsockname()[1]
    token = os.environ.get("PHI_GUARD_STUDIO_TOKEN") or StudioConfig().token
    extra = (args.host,) if args.allow_network and not is_loopback_host(args.host) else ()
    config = StudioConfig(host=args.host, port=port, token=token, data_dir=args.data_dir, extra_hosts=extra)

    import uvicorn

    from .app import create_app

    app = create_app(config)
    url = f"http://127.0.0.1:{port}/#token={token}"
    print(f"  Open this address in your browser:\n  {url}\n\n  Press Ctrl+C to stop Studio.\n", flush=True)
    if not args.no_browser:
        threading.Timer(0.8, webbrowser.open, [url]).start()
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False, server_header=False))
    server.run(sockets=[sock])
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
