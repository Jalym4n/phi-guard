"""One call that combines PHI redaction, injection screening, and audit logging."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .audit import AuditLog
from .detectors import Finding
from .injection import InjectionReport, analyze
from .redactor import Redactor

__all__ = ["Guard", "GuardResult"]


@dataclass
class GuardResult:
    text: str  # redacted text, safe to send onward
    findings: list[Finding]
    injection: InjectionReport | None
    allowed: bool

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.findings:
            out[f.kind] = out.get(f.kind, 0) + 1
        return out


class Guard:
    def __init__(self, redactor: Redactor | None = None, audit: AuditLog | None = None) -> None:
        self.redactor = redactor or Redactor()
        self.audit = audit

    def inspect(
        self,
        text: str,
        source: str = "user",
        untrusted: bool = False,
        kinds: Iterable[str] | None = None,
    ) -> GuardResult:
        """Redact PHI; if ``untrusted``, also screen for prompt injection.

        ``allowed`` is False only when the injection verdict is ``block``.
        """
        report = analyze(text) if untrusted else None
        result = self.redactor.redact(text, kinds)
        allowed = report is None or report.verdict != "block"
        if self.audit is not None:
            self.audit.append(
                "inspect",
                source=source,
                counts=result.counts(),
                untrusted=untrusted,
                verdict=report.verdict if report else None,
                score=round(report.score, 4) if report else None,
                allowed=allowed,
            )
        return GuardResult(result.text, result.findings, report, allowed)
