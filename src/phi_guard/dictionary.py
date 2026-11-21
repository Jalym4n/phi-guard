"""Custom word lists.

* **Always remove** terms (staff names, the clinic's name, a rare surname)
  are found with case-insensitive whole-word matching and reported as kind
  ``CUSTOM``.
* **Never remove** terms (a drug name that looks like a surname, the
  clinic's public phone number) suppress any detector finding whose text
  matches the term.

Matching ignores case and runs of whitespace.  For terms that are mostly
digits (phone numbers, fax numbers) only the digits are compared, so
``(905) 555-0100`` and ``905-555-0100`` are treated as the same term.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from .finding import Finding

__all__ = ["CUSTOM_CONFIDENCE", "Dictionary", "dump_terms", "parse_terms"]

CUSTOM_CONFIDENCE = 1.0


def parse_terms(text: str) -> list[str]:
    """Parse a word-list file: one term per line; blank lines and ``#`` comments ignored."""
    terms: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        term = " ".join(line.split())
        if not term or term.startswith("#"):
            continue
        key = term.casefold()
        if key not in seen:
            seen.add(key)
            terms.append(term)
    return terms


def dump_terms(terms: Iterable[str]) -> str:
    return "".join(f"{t}\n" for t in terms)


def _normalize(term: str) -> str:
    digits = re.sub(r"\D", "", term)
    if len(digits) >= 7 and len(digits) >= 0.6 * len(re.sub(r"\s", "", term)):
        return "#" + digits
    return " ".join(term.split()).casefold()


@dataclass
class Dictionary:
    always: list[str] = field(default_factory=list)
    never: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.always = parse_terms("\n".join(self.always))
        self.never = parse_terms("\n".join(self.never))
        self._never_keys = {_normalize(t) for t in self.never}
        self._always_re = self._compile(self.always)

    @staticmethod
    def _compile(terms: list[str]) -> re.Pattern[str] | None:
        if not terms:
            return None
        parts = []
        for term in sorted(terms, key=len, reverse=True):
            words = [re.escape(w) for w in term.split()]
            parts.append(r"\s+".join(words))
        return re.compile(r"(?<!\w)(?:" + "|".join(parts) + r")(?!\w)", re.IGNORECASE)

    def find(self, text: str) -> list[Finding]:
        """Return a ``CUSTOM`` finding for every always-remove term in ``text``."""
        if self._always_re is None:
            return []
        return [
            Finding("CUSTOM", m.start(), m.end(), m.group(0), CUSTOM_CONFIDENCE, "dictionary")
            for m in self._always_re.finditer(text)
        ]

    def allows(self, value: str) -> bool:
        """True if ``value`` is on the never-remove list."""
        return bool(self._never_keys) and _normalize(value) in self._never_keys

    def __bool__(self) -> bool:
        return bool(self.always or self.never)
