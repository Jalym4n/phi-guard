"""Canadian street address detection.

Matches a civic number, a capitalized street name, and a street type, with
an optional unit before or after::

    48 Maple Grove Crescent
    Unit 4, 120 King St W
    #12 - 300 Lakeshore Blvd
    55 Queen Street East, Suite 200

City, province, and postal code are not part of the match (postal codes have
their own detector).  French street forms ("rue", "chemin") and rural routes
are not covered; see ``docs/LEARNING.md``.
"""

from __future__ import annotations

import re

from .finding import Finding

__all__ = ["ADDRESS_CONFIDENCE", "ADDRESS_RE", "STREET_TYPES", "find_addresses"]

ADDRESS_CONFIDENCE = 0.85

STREET_TYPES = (
    "Street", "St", "Avenue", "Ave", "Road", "Rd", "Boulevard", "Blvd", "Drive", "Dr",
    "Court", "Ct", "Crescent", "Cres", "Lane", "Ln", "Way", "Place", "Pl",
    "Trail", "Trl", "Parkway", "Pkwy",
    # Further Canada Post street types (added in v0.2 after dev-split analysis).
    "Circle", "Cir", "Terrace", "Terr", "Gate", "Heights", "Hts", "Grove", "Line", "Sideroad", "Concession",
    "Close", "Square", "Sq", "Highway", "Hwy", "Row", "Path", "Landing", "Gardens", "Crossing", "Mews",
)  # fmt: skip

_UNIT_WORD = r"(?:Unit|Suite|Ste\.?|Apt\.?|Apartment)"
_PRE_UNIT = rf"(?:{_UNIT_WORD}\s*\#?\s*\d+[A-Za-z]?\s*[,\-]\s*|\#\s*\d+[A-Za-z]?\s*[,\-]?\s*|\d+[A-Za-z]?\s*-\s*(?=\d))"
_POST_UNIT = rf"(?:\s*,?\s*{_UNIT_WORD}\s*\#?\s*\d+[A-Za-z]?|\s*,?\s*\#\s*\d+[A-Za-z]?)"
_WORD = r"(?:[A-Z][a-zA-Z'\-]*\.?|\d+(?:st|nd|rd|th))"
_TYPE = "|".join(sorted(STREET_TYPES, key=len, reverse=True))
_DIRECTION = r"(?:North|South|East|West|NE|NW|SE|SW|N|S|E|W)"

ADDRESS_RE = re.compile(
    rf"(?<![\w#\-])(?:{_PRE_UNIT})?"
    rf"\d{{1,6}}[A-Za-z]?[ \t]+"
    rf"{_WORD}(?:[ \t]+{_WORD}){{0,3}}[ \t]+"
    rf"(?:{_TYPE})\b\.?"
    rf"(?:[ \t]+{_DIRECTION}\b\.?)?"
    rf"(?:{_POST_UNIT})?"
)


def find_addresses(text: str) -> list[Finding]:
    out: list[Finding] = []
    for m in ADDRESS_RE.finditer(text):
        value = m.group(0).rstrip(" ,")
        # A trailing period belongs to the sentence unless it ends an abbreviation like "St."
        out.append(Finding("ADDRESS", m.start(), m.start() + len(value), value, ADDRESS_CONFIDENCE, "address"))
    return out
