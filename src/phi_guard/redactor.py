"""Replace PHI with deterministic tokens (pseudonymize) or type labels (mask).

Pseudonymize mode turns ``123 456 782`` into ``[SIN_2311c0d1]``.  The suffix
is the first 8 hex characters of HMAC-SHA256(key, kind + value).  The same
value always maps to the same token under the same key, so an AI model can
still tell that two mentions refer to the same person, but nobody can
recompute the token without the key.

The mapping from token back to original value lives only in an in-memory
vault.  ``restore()`` uses it; ``forget()`` wipes it.

Studio needs two extra controls, both supported by ``redact()``:

* ``keep``: spans the user marked "Keep" (left as-is in the output).
* ``manual``: spans the user selected with "Also remove this".
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .detectors import resolve_overlaps, scan
from .finding import Finding

if TYPE_CHECKING:
    from .dictionary import Dictionary

__all__ = ["MANUAL_KINDS", "MODES", "TOKEN_RE", "RedactionResult", "Redactor", "manual_finding"]

MODES = ("pseudonymize", "mask")

#: Kinds offered by Studio's "Also remove this" picker (Name, Address, ID number, Other).
MANUAL_KINDS = ("PATIENT_NAME", "ADDRESS", "ID_NUMBER", "OTHER")

#: Matches tokens produced by pseudonymize mode, e.g. ``[PATIENT_NAME_a2b6c3d4]``.
TOKEN_RE = re.compile(r"\[(?P<kind>[A-Z][A-Z0-9_]*?)_(?P<digest>[0-9a-f]{8})\]")


def _load_key(key: bytes | str | None) -> bytes:
    if key is None:
        env = os.environ.get("PHI_GUARD_KEY")
        if env:
            return env.encode("utf-8")
        return secrets.token_bytes(32)
    if isinstance(key, str):
        return key.encode("utf-8")
    return bytes(key)


def manual_finding(text: str, start: int, end: int, kind: str = "OTHER") -> Finding:
    """Build a finding for a span the user selected by hand."""
    if not (0 <= start < end <= len(text)):
        raise ValueError(f"manual span {start}-{end} is outside the text")
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", kind):
        raise ValueError(f"invalid kind {kind!r}")
    return Finding(kind, start, end, text[start:end], 1.0, "manual")


@dataclass
class RedactionResult:
    text: str
    findings: list[Finding]  # what was replaced
    tokens: dict[str, str] = field(default_factory=dict)  # token -> kind (never the original value)
    kept: list[Finding] = field(default_factory=list)  # detected but kept at the user's request

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.findings:
            out[f.kind] = out.get(f.kind, 0) + 1
        return out


class Redactor:
    """Detect and replace PHI in text."""

    def __init__(self, key: bytes | str | None = None, mode: str = "pseudonymize") -> None:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
        self.mode = mode
        self._key = _load_key(key)
        self._vault: dict[str, str] = {}

    # -- tokens -----------------------------------------------------------
    def token_for(self, kind: str, value: str, mode: str | None = None) -> str:
        if (mode or self.mode) == "mask":
            return f"[{kind}]"
        normalized = " ".join(value.split()).casefold()
        digest = hmac.new(self._key, f"{kind}:{normalized}".encode(), hashlib.sha256).hexdigest()[:8]
        return f"[{kind}_{digest}]"

    # -- main API ---------------------------------------------------------
    def redact(
        self,
        text: str,
        kinds: Iterable[str] | None = None,
        *,
        dictionary: Dictionary | None = None,
        ner: bool = False,
        keep: Iterable[tuple[int, int]] = (),
        manual: Iterable[Finding] = (),
        mode: str | None = None,
    ) -> RedactionResult:
        """Scan ``text`` and replace what was found.

        ``keep`` lists ``(start, end)`` spans of detected findings to leave
        untouched.  Any detected finding *not* listed is removed: the safe
        default.  ``manual`` findings are always removed and win any overlap.
        """
        detected = scan(text, kinds, dictionary=dictionary, ner=ner)
        manual = list(manual)
        merged = resolve_overlaps([*detected, *manual]) if manual else detected
        keep_set = {tuple(s) for s in keep}
        to_remove = [f for f in merged if f.source == "manual" or f.span not in keep_set]
        kept = [f for f in merged if f.source != "manual" and f.span in keep_set]
        result = self.apply(text, to_remove, mode=mode)
        result.kept = kept
        return result

    def apply(self, text: str, findings: list[Finding], mode: str | None = None) -> RedactionResult:
        """Replace the given (non-overlapping) findings in ``text``."""
        mode = mode or self.mode
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
        pieces: list[str] = []
        tokens: dict[str, str] = {}
        cursor = 0
        ordered = sorted(findings, key=lambda f: f.start)
        for f in ordered:
            if f.start < cursor:
                raise ValueError("findings overlap")
            token = self.token_for(f.kind, f.text, mode)
            pieces.append(text[cursor : f.start])
            pieces.append(token)
            cursor = f.end
            tokens[token] = f.kind
            if mode == "pseudonymize":
                self._vault[token] = f.text
        pieces.append(text[cursor:])
        return RedactionResult("".join(pieces), ordered, tokens)

    def restore(self, text: str) -> str:
        """Put original values back for every token found in the vault."""
        return self.restore_detailed(text)[0]

    def restore_detailed(self, text: str) -> tuple[str, list[str]]:
        """Like ``restore`` but also return tokens that are not in the vault."""
        missing: list[str] = []

        def sub(m: re.Match[str]) -> str:
            token = m.group(0)
            if token in self._vault:
                return self._vault[token]
            if token not in missing:
                missing.append(token)
            return token

        return TOKEN_RE.sub(sub, text), missing

    def forget(self) -> None:
        """Wipe the vault.  Tokens can no longer be restored."""
        self._vault.clear()

    @property
    def vault_size(self) -> int:
        return len(self._vault)

    @property
    def known_tokens(self) -> frozenset[str]:
        return frozenset(self._vault)
