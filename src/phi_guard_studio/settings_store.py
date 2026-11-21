"""User settings, saved as JSON in the operating system's app-data folder.

Settings never contain patient text.  The custom word lists can contain
staff or patient names that the clinic chose to add; they stay on this
computer.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from phi_guard.detectors import ALL_KINDS
from phi_guard.dictionary import Dictionary, parse_terms

__all__ = ["Settings", "SettingsStore"]

MAX_TERMS = 5000


class Settings(BaseModel):
    enabled_kinds: list[str] = Field(default_factory=lambda: list(ALL_KINDS))
    always_remove: list[str] = Field(default_factory=list)
    never_remove: list[str] = Field(default_factory=list)
    default_mode: Literal["pseudonymize", "mask"] = "pseudonymize"
    text_size: Literal["normal", "large", "larger"] = "normal"
    theme: Literal["system", "light", "dark"] = "system"
    ner_enabled: bool = False
    ocr_enabled: bool = True  # read scanned PDFs and fax images (needs Tesseract)
    ocr_language: Literal["eng", "eng+fra"] = "eng"
    idle_timeout_minutes: int = Field(default=30, ge=1, le=480)
    max_upload_mb: int = Field(default=20, ge=1, le=100)
    batch_max_files: int = Field(default=200, ge=1, le=1000)
    batch_max_mb: int = Field(default=100, ge=1, le=500)

    @field_validator("enabled_kinds")
    @classmethod
    def _known_kinds(cls, v: list[str]) -> list[str]:
        unknown = set(v) - set(ALL_KINDS)
        if unknown:
            raise ValueError(f"unknown kinds: {sorted(unknown)}")
        return [k for k in ALL_KINDS if k in v]

    @field_validator("always_remove", "never_remove")
    @classmethod
    def _clean_terms(cls, v: list[str]) -> list[str]:
        terms = parse_terms("\n".join(v))
        if len(terms) > MAX_TERMS:
            raise ValueError(f"at most {MAX_TERMS} terms")
        return [t[:200] for t in terms]

    def dictionary(self) -> Dictionary | None:
        if not (self.always_remove or self.never_remove):
            return None
        return Dictionary(self.always_remove, self.never_remove)


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._settings = self._load()

    def _load(self) -> Settings:
        try:
            return Settings.model_validate(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError, ValidationError):
            return Settings()

    def get(self) -> Settings:
        return self._settings.model_copy(deep=True)

    def update(self, new: Settings) -> Settings:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(new.model_dump_json(indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
            self._settings = new
        return self.get()
