"""phi-guard: redact patient data and screen for prompt injection before text reaches an AI model."""

from .audit import AuditLog
from .detectors import ALL_KINDS, luhn_valid, scan
from .dictionary import Dictionary
from .finding import Finding
from .guard import Guard, GuardResult
from .injection import InjectionReport, analyze, wrap_untrusted
from .output_scan import scan_output
from .redactor import RedactionResult, Redactor

__version__ = "0.3.0"

__all__ = [
    "ALL_KINDS",
    "AuditLog",
    "Dictionary",
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
    "scan_output",
    "wrap_untrusted",
]
