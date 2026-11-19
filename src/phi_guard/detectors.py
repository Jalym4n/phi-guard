"""Regex detectors for Canadian PHI / PII.

Each detector is a compiled regular expression plus an optional validator
(for example, a Luhn checksum).  ``scan()`` runs every enabled detector,
then resolves overlaps so that each character belongs to at most one
finding.  When two findings overlap, the one with the higher priority wins;
ties go to the longer match.

Optional extra sources plug into the same overlap resolver:

* street addresses (``addresses.py``, kind ``ADDRESS``),
* custom "always remove" terms (``dictionary.py``, kind ``CUSTOM``),
* spaCy person names (``ner.py``, kind ``PERSON_NAME_NER``).

All offsets are Python string indices (Unicode code points); see
``finding.py`` for UTF-16 conversion.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .addresses import find_addresses
from .finding import Finding

if TYPE_CHECKING:
    from .dictionary import Dictionary

__all__ = [
    "ALL_KINDS",
    "DETECTORS",
    "EXTRA_KINDS",
    "KIND_PRIORITY",
    "Detector",
    "Finding",
    "luhn_valid",
    "resolve_overlaps",
    "scan",
]


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
    confidence: float = 0.9
    #: Skip numbers labelled as something harmless ("Order #", "Lot", "firmware").
    negative_context: bool = False

    def find(self, text: str) -> Iterable[Finding]:
        for m in self.pattern.finditer(text):
            group = "value" if "value" in self.pattern.groupindex else 0
            start, end = m.span(group)
            if start < 0 or start == end:
                continue
            value = text[start:end]
            if self.validator is not None and not self.validator(value):
                continue
            if self.negative_context and _NEGATIVE_CONTEXT_RE.search(text[max(0, start - 30) : start]):
                continue
            yield Finding(self.kind, start, end, value, self.confidence)


#: Labels that mean "the number after me is not about a person".
_NEGATIVE_CONTEXT_RE = re.compile(
    r"\b(?:order|requisition|req|accession|lot|batch|invoice|ref(?:erence)?|confirmation|specimen|barcode|"
    r"serial|firmware|version|ver|build|catalog(?:ue)?|item|sku|model|v)\.?"
    r"\s*(?:#|no\.?|num(?:ber)?|id|code)?\s*[:#]?\s*$",
    re.IGNORECASE,
)


_SEP = r"[ \-]?"
_DATE = (
    r"(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"  # 1984-03-12
    r"|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}"  # 12/03/1984
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"
    r"|\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?,?\s+\d{4})"
)
_NAME_WORD = r"[A-Z][a-zA-Z'\-]+"
_NAME = rf"{_NAME_WORD}(?:\s+[A-Z]\.)?(?:[ \t]+{_NAME_WORD}){{0,2}}"
# "Whitfield, Eleanor" (surname first), common in charts and requisitions.
_NAME_OR_REVERSED = rf"(?:{_NAME_WORD},[ \t]*{_NAME_WORD}(?:[ \t]+[A-Z]\.)?|{_NAME})"
_NOT_TITLE = r"(?!(?:Dr|Mr|Mrs|Ms|Miss|Mx|Prof)\b)"
_RELATION = (
    r"(?:daughter|son|husband|wife|partner|spouse|sister|brother|mother|father|caregiver|friend|niece|nephew|"
    r"grandson|granddaughter|guardian)"
)

DETECTORS: tuple[Detector, ...] = (
    Detector(
        "OHIP_NUMBER",
        re.compile(rf"(?<![\d\-])(?P<value>\d{{4}}{_SEP}\d{{3}}{_SEP}\d{{3}}(?:[ \-]?[A-Z]{{2}}\b)?)(?![\d\-])"),
        priority=100,
        validator=_valid_ohip,
        confidence=0.99,
        negative_context=True,
    ),
    Detector(
        "SIN",
        re.compile(r"(?<![\d\-])(?P<value>\d{3}[ \-]?\d{3}[ \-]?\d{3})(?![\d\-])"),
        priority=95,
        validator=_valid_sin,
        confidence=0.99,
        negative_context=True,
    ),
    Detector(
        "CREDIT_CARD",
        re.compile(r"(?<![\d\-])(?P<value>\d{4}(?:[ \-]?\d{4}){2}[ \-]?\d{1,7})(?![\d\-])"),
        priority=90,
        validator=_valid_card,
        confidence=0.99,
        negative_context=True,
    ),
    Detector(
        "EMAIL",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        priority=85,
        confidence=0.98,
    ),
    Detector(
        "MRN",
        re.compile(
            r"\b(?:MRN|Medical\s+Record\s+(?:Number|No\.?|#)|Chart\s*(?:Number|No\.?|#)|Patient\s+ID|"
            r"Hospital\s*(?:Number|No\.?|#)|Health\s+Record\s*(?:Number|No\.?|#))"
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
        negative_context=True,
    ),
    # Ten digits with no separators are only a phone number if something says so.
    Detector(
        "PHONE",
        re.compile(
            r"(?i:\b(?:phone|tel|telephone|cell|mobile|contact|call|home|work|fax)\b)[^\n\d]{0,15}"
            r"(?P<value>(?:\+?1)?\d{10})(?!\d)"
        ),
        priority=70,
        confidence=0.85,
    ),
    Detector(
        "IP_ADDRESS",
        re.compile(r"(?<![\d.])(?P<value>(?:\d{1,3}\.){3}\d{1,3})(?!\.?\d)"),
        priority=65,
        validator=_valid_ipv4,
        negative_context=True,
    ),
    Detector(
        "POSTAL_CODE",
        re.compile(r"\b[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z][ \-]?\d[ABCEGHJ-NPRSTV-Z]\d\b", re.IGNORECASE),
        priority=60,
    ),
    # A labelled name ("Patient: Jane Doe", "Emergency contact: ...") is a strong cue.
    Detector(
        "PATIENT_NAME",
        re.compile(
            r"(?i:\b(?:Patient(?:\s+Name)?|Pt|Name|Client|Resident|Re|Emergency\s+Contact|Next\s+of\s+Kin|"
            r"Contact\s+Person|Substitute\s+Decision[\s\-]Maker|SDM|Guardian))[ \t]*[:\-][ \t]*"
            rf"{_NOT_TITLE}(?P<value>{_NAME_OR_REVERSED})"
        ),
        priority=50,
        confidence=0.85,
    ),
    # Referral-letter and relative cues: "Thank you for seeing Jane Doe", "her daughter, Ann Doe".
    Detector(
        "PATIENT_NAME",
        re.compile(
            rf"(?:(?i:\bThank\s+you\s+for\s+(?:seeing|assessing|reviewing))|"
            rf"(?i:\b(?:his|her|their|the\s+patient's)\s+{_RELATION})\s*,?)\s+{_NOT_TITLE}(?P<value>{_NAME})"
        ),
        priority=50,
        confidence=0.8,
    ),
    # An honorific ("Mrs. Doe") is weaker: it also matches staff and family members.
    Detector(
        "PATIENT_NAME",
        re.compile(rf"\b(?:Mr|Mrs|Ms|Miss|Mx)\.?\s+(?P<value>{_NAME})"),
        priority=50,
        confidence=0.8,
    ),
)

#: Kinds that can be switched on and off individually.
ALL_KINDS: tuple[str, ...] = (*dict.fromkeys(d.kind for d in DETECTORS), "ADDRESS")

#: Kinds produced by other sources (custom word lists, NER, manual selection in Studio).
EXTRA_KINDS: tuple[str, ...] = ("CUSTOM", "PERSON_NAME_NER", "ID_NUMBER", "OTHER")

#: Higher wins when findings overlap.  Manual selections and custom terms beat
#: every detector because the user asked for them explicitly.
KIND_PRIORITY: dict[str, int] = {
    "MANUAL": 200,
    "CUSTOM": 110,
    **{d.kind: d.priority for d in DETECTORS},
    "ADDRESS": 55,
    "PERSON_NAME_NER": 40,
}


def resolve_overlaps(findings: Iterable[Finding], priorities: dict[str, int] | None = None) -> list[Finding]:
    """Keep the best finding wherever findings overlap.

    Greedy: sort by priority (highest first), then length (longest first),
    then position; accept a finding only if it does not overlap one already
    accepted.  Returns findings sorted by start offset.  Findings whose
    ``source`` is ``"manual"`` use the ``MANUAL`` priority whatever their kind;
    propagated name repeats rank lowest.
    """
    prio = priorities if priorities is not None else KIND_PRIORITY

    def rank(f: Finding) -> int:
        if f.source == "manual":
            return prio.get("MANUAL", 200)
        if f.source == "propagation":
            return 1  # a repeat of an existing name never displaces another finding
        return prio.get(f.kind, 0)

    ordered = sorted(findings, key=lambda f: (-rank(f), -(f.end - f.start), f.start))
    kept: list[Finding] = []
    for f in ordered:
        if not any(f.overlaps(k) for k in kept):
            kept.append(f)
    return sorted(kept, key=lambda f: (f.start, f.end))


#: Capitalized words that are never propagated as names on their own.
_PROPAGATION_STOPWORDS = frozenset(
    "Patient Name Client Resident Contact Emergency Doctor Nurse The This That And For With From Date Health Card "
    "Clinic Hospital Centre Center Street Road Avenue Drive January February March April May June July August "
    "September October November December Monday Tuesday Wednesday Thursday Friday Saturday Sunday".split()
)
PROPAGATION_CONFIDENCE = 0.75


def _propagate_names(text: str, findings: list[Finding]) -> list[Finding]:
    """Find later mentions of names already found with a cue.

    If "Patient: Eleanor Whitfield" was found, then "Eleanor" and "Whitfield"
    elsewhere in the same text are very likely the same person.  This is a
    standard de-identification technique (sometimes called name propagation).
    Matching is case-sensitive and whole-word.
    """
    tokens: set[str] = set()
    for f in findings:
        if f.kind == "PATIENT_NAME":
            for tok in re.split(r"[\s,]+", f.text):
                tok = tok.strip(".")
                if len(tok) >= 3 and tok[0].isupper() and tok not in _PROPAGATION_STOPWORDS:
                    tokens.add(tok)
    if not tokens:
        return []
    pattern = re.compile(
        r"(?<![\w'\-])(?:" + "|".join(map(re.escape, sorted(tokens, key=len, reverse=True))) + r")(?![\w'\-])"
    )
    return [
        Finding("PATIENT_NAME", m.start(), m.end(), m.group(0), PROPAGATION_CONFIDENCE, "propagation")
        for m in pattern.finditer(text)
    ]


def scan(
    text: str,
    kinds: Iterable[str] | None = None,
    *,
    dictionary: Dictionary | None = None,
    ner: bool = False,
) -> list[Finding]:
    """Find PHI/PII in ``text``.

    ``kinds`` limits the search to the given detector kinds (default: all of
    ``ALL_KINDS``).  ``dictionary`` adds always-remove terms and suppresses
    never-remove terms.  ``ner=True`` adds spaCy person names (needs the
    ``[ner]`` extra; raises ``ner.NerUnavailable`` otherwise).
    """
    wanted = set(kinds) if kinds is not None else set(ALL_KINDS)
    unknown = wanted - set(ALL_KINDS)
    if unknown:
        raise ValueError(f"unknown kinds: {sorted(unknown)}")
    found: list[Finding] = []
    for det in DETECTORS:
        if det.kind in wanted:
            found.extend(det.find(text))
    if "ADDRESS" in wanted:
        found.extend(find_addresses(text))
    if ner:
        from .ner import find_person_names

        found.extend(find_person_names(text))
    if dictionary is not None:
        # Never-remove terms suppress detector findings *before* overlap
        # resolution, so a lower-priority finding underneath can still win.
        found = [f for f in found if not dictionary.allows(f.text)]
        found.extend(dictionary.find(text))
    resolved = resolve_overlaps(found)
    if "PATIENT_NAME" in wanted:
        extra = _propagate_names(text, resolved)
        if dictionary is not None:
            extra = [f for f in extra if not dictionary.allows(f.text)]
        if extra:
            # Existing findings win overlaps because propagation has the lowest rank.
            resolved = resolve_overlaps([*resolved, *extra])
    return resolved
