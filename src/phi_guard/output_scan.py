"""Scan AI responses for patient details before showing them.

After redaction, a model should only ever see and return tokens like
``[PATIENT_NAME_a2b6c3d4]``.  If its answer contains a real-looking phone
number or name, either the model leaked something from elsewhere in its
context or it invented a plausible identifier.  Both deserve a second look.

Tokens are blanked out (replaced by spaces of equal length, so offsets stay
correct) before scanning, so the hex digits inside a token never trigger a
detector.  If ``known_tokens`` is given, token-shaped strings that are *not*
known are reported as ``UNKNOWN_TOKEN``: a sign the model fabricated one.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from typing import TYPE_CHECKING

from .detectors import scan
from .finding import Finding
from .redactor import TOKEN_RE

if TYPE_CHECKING:
    from .dictionary import Dictionary

__all__ = ["UNKNOWN_TOKEN_CONFIDENCE", "scan_output"]

UNKNOWN_TOKEN_CONFIDENCE = 0.6


def scan_output(
    text: str,
    known_tokens: Collection[str] | None = None,
    kinds: Iterable[str] | None = None,
    *,
    dictionary: Dictionary | None = None,
) -> list[Finding]:
    unknown: list[Finding] = []
    chars = list(text)
    for m in TOKEN_RE.finditer(text):
        for i in range(m.start(), m.end()):
            chars[i] = " "
        if known_tokens is not None and m.group(0) not in known_tokens:
            unknown.append(Finding("UNKNOWN_TOKEN", m.start(), m.end(), m.group(0), UNKNOWN_TOKEN_CONFIDENCE, "output"))
    blanked = "".join(chars)
    found = [
        Finding(f.kind, f.start, f.end, text[f.start : f.end], f.confidence, f.source)
        for f in scan(blanked, kinds, dictionary=dictionary)
    ]
    return sorted([*found, *unknown], key=lambda f: f.start)
