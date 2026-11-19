"""phi-guard: redact patient data and screen for prompt injection before text reaches an AI model."""

from .audit import AuditLog
from .detectors import ALL_KINDS, Finding, luhn_valid, scan
from .guard import Guard, GuardResult
from .injection import InjectionReport, analyze, wrap_untrusted
from .redactor import RedactionResult, Redactor

__version__ = "0.1.0"

__all__ = [
    "ALL_KINDS",
    "AuditLog",
    "Finding",
    "Guard",
    "GuardResult",
    "InjectionReport",
    "RedactionResult",
    "Redactor",
    "__version__",
    "analyze",
    "luhn_valid",
    "scan",
    "wrap_untrusted",
]
