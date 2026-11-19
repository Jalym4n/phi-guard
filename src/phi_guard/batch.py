"""Redact many documents at once and produce a summary sheet.

Used by ``phi-guard batch`` and by Studio's batch tab.  The summary CSV
contains file names, counts per type, and the injection verdict.  It never
contains original values.

Cells that start with ``=``, ``+``, ``-``, ``@`` (or tab / carriage return)
are prefixed with ``'`` so a spreadsheet does not execute a file name as a
formula (CSV injection).
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from .detectors import ALL_KINDS
from .documents import SUPPORTED_EXTENSIONS, DocumentError, docx_with_replacements, extract_text
from .injection import analyze
from .redactor import Redactor

if TYPE_CHECKING:
    from .dictionary import Dictionary

__all__ = ["BatchItem", "iter_folder", "output_name", "process_file", "run_batch", "summary_csv", "write_zip"]


@dataclass
class BatchItem:
    name: str
    status: str  # "done" | "skipped" | "error"
    reason: str = ""
    counts: dict[str, int] = field(default_factory=dict)
    verdict: str = ""
    score: float = 0.0
    output_name: str = ""
    output: bytes = field(default=b"", repr=False)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "reason": self.reason,
            "counts": self.counts,
            "verdict": self.verdict,
            "score": round(self.score, 4),
            "output_name": self.output_name,
        }


def output_name(name: str) -> str:
    """Redacted output keeps the name and folder; PDFs become .txt (text only)."""
    p = PurePosixPath(name.replace("\\", "/"))
    return str(p.with_suffix(".txt")) if p.suffix.lower() == ".pdf" else str(p)


def process_file(
    name: str,
    data: bytes,
    redactor: Redactor,
    *,
    kinds: Iterable[str] | None = None,
    dictionary: Dictionary | None = None,
    ner: bool = False,
    mode: str | None = None,
) -> BatchItem:
    """Redact one file.  ``mode`` overrides the redactor's default mode."""
    suffix = PurePosixPath(name).suffix.lower()
    base = PurePosixPath(name.replace("\\", "/")).name
    if base.startswith(".") or suffix not in SUPPORTED_EXTENSIONS:
        return BatchItem(name, "skipped", "Not a .txt, .docx or .pdf file")
    try:
        doc = extract_text(data, base)
    except DocumentError as exc:
        return BatchItem(name, "error", str(exc))
    kinds_list = list(kinds) if kinds is not None else None
    result = redactor.redact(doc.text, kinds_list, dictionary=dictionary, ner=ner, mode=mode)
    report = analyze(doc.text)
    if doc.kind == "docx":
        spans = [(f.start, f.end, redactor.token_for(f.kind, f.text, mode)) for f in result.findings]
        output = docx_with_replacements(data, spans)
    else:
        output = result.text.encode("utf-8")
    reason = " ".join(doc.warnings)
    return BatchItem(name, "done", reason, result.counts(), report.verdict, report.score, output_name(name), output)


def run_batch(
    files: Iterable[tuple[str, bytes]],
    redactor: Redactor,
    *,
    kinds: Iterable[str] | None = None,
    dictionary: Dictionary | None = None,
    ner: bool = False,
    progress: Callable[[int, BatchItem], None] | None = None,
) -> list[BatchItem]:
    kinds_list = list(kinds) if kinds is not None else None
    items: list[BatchItem] = []
    for i, (name, data) in enumerate(files, 1):
        item = process_file(name, data, redactor, kinds=kinds_list, dictionary=dictionary, ner=ner)
        items.append(item)
        if progress is not None:
            progress(i, item)
    return items


def _safe_cell(value: object) -> object:
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def summary_csv(items: Iterable[BatchItem]) -> str:
    items = list(items)
    extra = sorted({k for it in items for k in it.counts} - set(ALL_KINDS))
    kind_cols = [*ALL_KINDS, *extra]
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["file", "status", "reason", "total_found", *kind_cols, "injection_verdict", "injection_score"])
    for it in items:
        row: list[object] = [it.name, it.status, it.reason, sum(it.counts.values())]
        row += [it.counts.get(k, 0) for k in kind_cols]
        row += [it.verdict, f"{it.score:.2f}" if it.status == "done" else ""]
        writer.writerow([_safe_cell(c) for c in row])
    return buf.getvalue()


def write_zip(items: Iterable[BatchItem]) -> bytes:
    items = list(items)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for it in items:
            if it.status == "done":
                zf.writestr(f"redacted/{it.output_name}", it.output)
        zf.writestr("summary.csv", summary_csv(items))
    return buf.getvalue()


def iter_folder(folder: str | Path, recursive: bool = True) -> Iterable[tuple[str, Path]]:
    root = Path(folder)
    paths = root.rglob("*") if recursive else root.glob("*")
    for p in sorted(paths):
        if p.is_file():
            yield p.relative_to(root).as_posix(), p
