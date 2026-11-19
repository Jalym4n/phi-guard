"""Regex detectors for Canadian PHI / PII.

Each detector is a compiled regular expression plus an optional validator
(for example, a Luhn checksum).  ``scan()`` runs every enabled detector,
then resolves overlaps so that each character belongs to at most one
finding.  When two findings overlap, the one with the higher priority wins;
ties go to the longer match.

All offsets are Python string indices (Unicode code points).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

__all__ = [
    "ALL_KINDS",
    "DETECTORS",
    "Detector",
    "Finding",
    "luhn_valid",
    "resolve_overlaps",
    "scan",
]


@dataclass(frozen=True)
class Finding:
    """One piece of personal information found in a text."""

    kind: str
    start: int
    end: int
    text: str

    def overlaps(self, other: Finding) -> bool:
        return self.start < other.end and other.start < self.end

    def to_dict(self) -> dict[str, object]:
        return {"kind": self.kind, "start": self.start, "end": self.end, "text": self.text}


def luhn_valid(digits: str) -> bool:
    """Return True if ``digits`` passes the Luhn (mod 10) checksum.

    Starting from the rightmost digit, double every second digit; if the
    doubled value is over 9, subtract 9.  The total must be divisible by 10.
    Used by SINs, Ontario health card numbers, and payment cards.
    """
    if not digits.isdigit() or len(digits) < 2:
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def _valid_sin(s: str) -> bool:
    d = _digits(s)
    # SINs never start with 0 or 8 (8 is unassigned).
    return len(d) == 9 and d[0] not in "08" and luhn_valid(d)


def _valid_ohip(s: str) -> bool:
    d = _digits(s)
    return len(d) == 10 and luhn_valid(d)


def _valid_card(s: str) -> bool:
    d = _digits(s)
    return 13 <= len(d) <= 19 and luhn_valid(d)


def _valid_ipv4(s: str) -> bool:
    parts = s.split(".")
    return len(parts) == 4 and all(p.isdigit() and int(p) <= 255 and (p == "0" or not p.startswith("0")) for p in parts)


@dataclass(frozen=True)
class Detector:
    """A named regex with a priority and an optional validator.

    If the pattern contains a group called ``value``, only that group becomes
    the finding.  This lets a detector require context ("DOB:") without
    redacting the label itself.
    """

    kind: str
    pattern: re.Pattern[str]
    priority: int
    validator: Callable[[str], bool] | None = None

    def find(self, text: str) -> Iterable[Finding]:
        for m in self.pattern.finditer(text):
            group = "value" if "value" in self.pattern.groupindex else 0
            start, end = m.span(group)
            if start < 0 or start == end:
                continue
            value = text[start:end]
            if self.validator is not None and not self.validator(value):
                continue
            yield Finding(self.kind, start, end, value)


_SEP = r"[ \-]?"
_DATE = (
    r"(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"  # 1984-03-12
    r"|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}"  # 12/03/1984
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"
    r"|\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?,?\s+\d{4})"
)
_NAME_WORD = r"[A-Z][a-zA-Z'\-]+"
_NAME = rf"{_NAME_WORD}(?:\s+[A-Z]\.)?(?:[ \t]+{_NAME_WORD}){{0,2}}"

DETECTORS: tuple[Detector, ...] = (
    Detector(
        "OHIP_NUMBER",
        re.compile(rf"(?<![\d\-])(?P<value>\d{{4}}{_SEP}\d{{3}}{_SEP}\d{{3}}(?:[ \-]?[A-Z]{{2}}\b)?)(?![\d\-])"),
        priority=100,
        validator=_valid_ohip,
    ),
    Detector(
        "SIN",
        re.compile(r"(?<![\d\-])(?P<value>\d{3}[ \-]?\d{3}[ \-]?\d{3})(?![\d\-])"),
        priority=95,
        validator=_valid_sin,
    ),
    Detector(
        "CREDIT_CARD",
        re.compile(r"(?<![\d\-])(?P<value>\d{4}(?:[ \-]?\d{4}){2}[ \-]?\d{1,7})(?![\d\-])"),
        priority=90,
        validator=_valid_card,
    ),
    Detector(
        "EMAIL",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        priority=85,
    ),
    Detector(
        "MRN",
        re.compile(
            r"\b(?:MRN|Medical\s+Record\s+(?:Number|No\.?|#)|Chart\s*(?:Number|No\.?|#)|Patient\s+ID)"
            r"\s*[:#]?\s*(?P<value>[A-Z]{0,3}-?\d{5,10})\b",
            re.IGNORECASE,
        ),
        priority=80,
    ),
    Detector(
        "DATE_OF_BIRTH",
        re.compile(
            r"\b(?:DOB|D\.O\.B\.?|Date\s+of\s+Birth|Birth\s*date|Born(?:\s+on)?)\s*[:\-]?\s*"
            rf"(?P<value>{_DATE})",
            re.IGNORECASE,
        ),
        priority=75,
    ),
    Detector(
        "PHONE",
        re.compile(
            r"(?<![\w\-])(?P<value>(?:\+?1[ .\-]?)?(?:\(\d{3}\)\s?|\d{3}[ .\-])\d{3}[ .\-]\d{4})"
            r"(?:\s*(?:x|ext\.?)\s*\d{1,5})?(?![\w\-])"
        ),
        priority=70,
    ),
    Detector(
        "IP_ADDRESS",
        re.compile(r"(?<![\d.])(?P<value>(?:\d{1,3}\.){3}\d{1,3})(?!\.?\d)"),
        priority=65,
        validator=_valid_ipv4,
    ),
    Detector(
        "POSTAL_CODE",
        re.compile(r"\b[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z][ \-]?\d[ABCEGHJ-NPRSTV-Z]\d\b"),
        priority=60,
    ),
    Detector(
        "PATIENT_NAME",
        re.compile(
            r"(?:\b(?:Patient(?:\s+Name)?|Pt|Name|Client|Resident)\s*[:\-]\s*"
            r"|\b(?:Mr|Mrs|Ms|Miss|Mx)\.?\s+)"
            rf"(?P<value>{_NAME})"
        ),
        priority=50,
    ),
)

ALL_KINDS: tuple[str, ...] = tuple(d.kind for d in DETECTORS)


def resolve_overlaps(findings: Iterable[Finding], priorities: dict[str, int] | None = None) -> list[Finding]:
    """Keep the best finding wherever findings overlap.

    Greedy: sort by priority (highest first), then length (longest first),
    then position; accept a finding only if it does not overlap one already
    accepted.  Returns findings sorted by start offset.
    """
    prio = priorities if priorities is not None else {d.kind: d.priority for d in DETECTORS}
    ordered = sorted(findings, key=lambda f: (-prio.get(f.kind, 0), -(f.end - f.start), f.start))
    kept: list[Finding] = []
    for f in ordered:
        if not any(f.overlaps(k) for k in kept):
            kept.append(f)
    return sorted(kept, key=lambda f: (f.start, f.end))


def scan(text: str, kinds: Iterable[str] | None = None) -> list[Finding]:
    """Find PHI/PII in ``text``.

    ``kinds`` limits the search to the given detector kinds (default: all).
    """
    wanted = set(kinds) if kinds is not None else set(ALL_KINDS)
    unknown = wanted - set(ALL_KINDS)
    if unknown:
        raise ValueError(f"unknown kinds: {sorted(unknown)}")
    found: list[Finding] = []
    for det in DETECTORS:
        if det.kind in wanted:
            found.extend(det.find(text))
    return resolve_overlaps(found)
