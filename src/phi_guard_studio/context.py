"""Shared objects for one running Studio, attached to ``app.state.studio``."""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Request

from phi_guard.audit import AuditLog

from .config import StudioConfig
from .keystore import KeyStore
from .settings_store import SettingsStore
from .state import SessionState

__all__ = ["Studio", "get_studio"]


@dataclass
class Studio:
    config: StudioConfig
    settings: SettingsStore
    keystore: KeyStore
    session: SessionState
    audit: AuditLog
    ner_available: bool = False
    port: int = field(default=0)

    def audit_event(self, event: str, **fields: object) -> None:
        """Write an audit entry.  Callers pass counts and verdicts only, never text."""
        self.audit.append(event, source="studio", **fields)


def get_studio(request: Request) -> Studio:
    studio: Studio = request.app.state.studio
    return studio
