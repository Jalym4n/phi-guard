"""The ``Finding`` type shared by every detector, plus Unicode offset helpers.

Python indexes strings by Unicode code point.  Browsers (JavaScript) index by
UTF-16 code unit, where characters outside the Basic Multilingual Plane
(most emoji, some CJK) take two units.  ``to_utf16`` and ``from_utf16``
convert between the two so highlights line up in the UI.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Finding", "from_utf16", "to_utf16", "utf16_index_map"]


@dataclass(frozen=True)
class Finding:
    """One piece of personal information found in a text.

    ``start``/``end`` are code-point offsets into the scanned text.
    ``confidence`` is a fixed per-detector estimate in [0, 1]; values below
    0.85 are shown to users as "Please check".
    """

    kind: str
    start: int
    end: int
    text: str
    confidence: float = 1.0
    source: str = "regex"  # regex | address | dictionary | ner | manual

    def overlaps(self, other: Finding) -> bool:
        return self.start < other.end and other.start < self.end

    @property
    def span(self) -> tuple[int, int]:
        return (self.start, self.end)

    def to_dict(self, include_text: bool = True) -> dict[str, object]:
        d: dict[str, object] = {
            "kind": self.kind,
            "start": self.start,
            "end": self.end,
            "confidence": self.confidence,
            "source": self.source,
        }
        if include_text:
            d["text"] = self.text
        return d


def utf16_index_map(text: str) -> list[int]:
    """``m[i]`` is the UTF-16 offset of code point ``i``; ``m[len(text)]`` is the total length."""
    out = [0] * (len(text) + 1)
    pos = 0
    for i, ch in enumerate(text):
        out[i] = pos
        pos += 2 if ord(ch) > 0xFFFF else 1
    out[len(text)] = pos
    return out


def to_utf16(text: str, index: int) -> int:
    """Convert a code-point offset in ``text`` to a UTF-16 offset."""
    return index + sum(1 for ch in text[:index] if ord(ch) > 0xFFFF)


def from_utf16(text: str, index16: int) -> int:
    """Convert a UTF-16 offset in ``text`` to a code-point offset.

    An offset that falls in the middle of a surrogate pair is rounded down.
    """
    pos = 0
    for i, ch in enumerate(text):
        width = 2 if ord(ch) > 0xFFFF else 1
        if pos + width > index16:
            return i
        pos += width
    return len(text)
