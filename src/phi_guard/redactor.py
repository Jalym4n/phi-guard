"""Replace PHI with deterministic tokens (pseudonymize) or type labels (mask).

Pseudonymize mode turns ``123 456 782`` into ``[SIN_2311c0d1]``.  The suffix
is the first 8 hex characters of HMAC-SHA256(key, kind + value).  The same
value always maps to the same token under the same key, so an AI model can
still tell that two mentions refer to the same person, but nobody can
recompute the token without the key.

The mapping from token back to original value lives only in an in-memory
vault.  ``restore()`` uses it; ``forget()`` wipes it.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from collections.abc import Iterable
from dataclasses import dataclass, field

from .detectors import Finding, scan

__all__ = ["MODES", "TOKEN_RE", "RedactionResult", "Redactor"]

MODES = ("pseudonymize", "mask")

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


@dataclass
class RedactionResult:
    text: str
    findings: list[Finding]
    tokens: dict[str, str] = field(default_factory=dict)  # token -> kind (never the original value)

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
    def token_for(self, kind: str, value: str) -> str:
        if self.mode == "mask":
            return f"[{kind}]"
        normalized = " ".join(value.split()).casefold()
        digest = hmac.new(self._key, f"{kind}:{normalized}".encode(), hashlib.sha256).hexdigest()[:8]
        return f"[{kind}_{digest}]"

    # -- main API ---------------------------------------------------------
    def redact(self, text: str, kinds: Iterable[str] | None = None) -> RedactionResult:
        findings = scan(text, kinds)
        return self.apply(text, findings)

    def apply(self, text: str, findings: list[Finding]) -> RedactionResult:
        """Replace the given (non-overlapping) findings in ``text``."""
        pieces: list[str] = []
        tokens: dict[str, str] = {}
        cursor = 0
        for f in sorted(findings, key=lambda f: f.start):
            if f.start < cursor:
                raise ValueError("findings overlap")
            token = self.token_for(f.kind, f.text)
            pieces.append(text[cursor : f.start])
            pieces.append(token)
            cursor = f.end
            tokens[token] = f.kind
            if self.mode == "pseudonymize":
                self._vault[token] = f.text
        pieces.append(text[cursor:])
        return RedactionResult("".join(pieces), list(findings), tokens)

    def restore(self, text: str) -> str:
        """Put original values back for every token found in the vault."""
        return TOKEN_RE.sub(lambda m: self._vault.get(m.group(0), m.group(0)), text)

    def forget(self) -> None:
        """Wipe the vault.  Tokens can no longer be restored."""
        self._vault.clear()

    @property
    def vault_size(self) -> int:
        return len(self._vault)
