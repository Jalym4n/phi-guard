"""Runtime configuration for one Studio launch."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from pathlib import Path

from platformdirs import user_data_dir

__all__ = ["DEFAULT_DATA_DIR", "StudioConfig"]

DEFAULT_DATA_DIR = Path(user_data_dir("phi-guard-studio", appauthor=False))


@dataclass
class StudioConfig:
    host: str = "127.0.0.1"
    port: int = 0
    #: Per-launch secret the browser must send in the ``X-PHI-Guard-Token`` header.
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    data_dir: Path = DEFAULT_DATA_DIR
    #: Extra Host header values to accept (``--allow-network`` only).
    extra_hosts: tuple[str, ...] = ()
    #: Directory holding the built frontend.  ``None`` uses the packaged ``static/`` folder.
    static_dir: Path | None = None

    @property
    def audit_path(self) -> Path:
        return self.data_dir / "audit.jsonl"

    @property
    def settings_path(self) -> Path:
        return self.data_dir / "settings.json"
