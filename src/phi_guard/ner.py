"""Optional person-name detection with spaCy (install the ``[ner]`` extra).

Regex name detection needs a cue ("Patient:", "Mrs.").  A statistical named
entity recognizer can find names without a cue, at the cost of speed, a
large model download, and some false positives (drug and place names).
Findings use kind ``PERSON_NAME_NER`` and a fixed confidence of 0.7, so the
UI asks the user to check them.

Everything in phi-guard works without this module's dependencies.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from .finding import Finding

__all__ = ["DEFAULT_MODEL", "NER_CONFIDENCE", "NerUnavailable", "find_person_names", "is_available"]

DEFAULT_MODEL = "en_core_web_sm"
NER_CONFIDENCE = 0.7


class NerUnavailable(RuntimeError):
    """spaCy or its English model is not installed."""


@lru_cache(maxsize=2)
def _load(model: str) -> Any:
    try:
        import spacy
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise NerUnavailable("Install the optional extra: pip install 'phi-guard[ner]'") from exc
    try:
        return spacy.load(model, disable=["lemmatizer", "textcat"])
    except OSError as exc:  # pragma: no cover - depends on environment
        raise NerUnavailable(f"spaCy model {model!r} is not installed: python -m spacy download {model}") from exc


def is_available(model: str = DEFAULT_MODEL) -> bool:
    try:
        _load(model)
    except NerUnavailable:
        return False
    return True


def find_person_names(text: str, model: str = DEFAULT_MODEL) -> list[Finding]:
    nlp = _load(model)
    doc = nlp(text)
    out: list[Finding] = []
    for ent in doc.ents:
        if ent.label_ != "PERSON":
            continue
        value = ent.text.strip()
        if len(value) < 2 or not any(ch.isalpha() for ch in value):
            continue
        start = ent.start_char + (len(ent.text) - len(ent.text.lstrip()))
        out.append(Finding("PERSON_NAME_NER", start, start + len(value), value, NER_CONFIDENCE, "ner"))
    return out
