"""Request and response models.  All offsets sent to or from the browser are UTF-16 code units."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MAX_TEXT = 2_000_000  # characters


class TextIn(BaseModel):
    text: str = Field(max_length=MAX_TEXT)


class ScanIn(TextIn):
    kinds: list[str] | None = None


class Span(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class ManualSpan(Span):
    kind: Literal["PATIENT_NAME", "ADDRESS", "ID_NUMBER", "OTHER"] = "OTHER"


class RedactIn(TextIn):
    mode: Literal["pseudonymize", "mask"] = "pseudonymize"
    keep: list[Span] = Field(default_factory=list, max_length=10_000)
    manual: list[ManualSpan] = Field(default_factory=list, max_length=10_000)
    final: bool = False  # True when the user copies or downloads (written to the activity log)


class FindingOut(BaseModel):
    id: str
    kind: str
    label: str
    start: int
    end: int
    text: str
    confidence: float
    needs_check: bool
    source: str


class PasswordIn(BaseModel):
    password: str = Field(min_length=1, max_length=1024)
