"""Extract text from .txt, .docx, and .pdf files, and write redacted .docx copies.

The core library stays dependency-free: ``python-docx`` and ``pypdf`` are
imported only when a .docx or .pdf is actually opened (install the
``[studio]`` or ``[docs]`` extra).

File types are decided by *content* (magic bytes), not by the extension, so
a renamed executable is rejected even if it is called ``notes.txt``.

All work happens in memory.  Nothing is written to a temporary file.

Redacted .docx output keeps the paragraph and table structure.  Inside a
paragraph that contained patient details, character formatting (bold,
italic) is simplified to the formatting of the paragraph's first run.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "SUPPORTED_EXTENSIONS",
    "DocumentError",
    "ExtractedDocument",
    "ScannedPdfError",
    "UnsupportedDocument",
    "detect_kind",
    "docx_with_replacements",
    "extract_text",
]

SUPPORTED_EXTENSIONS = (".txt", ".docx", ".pdf")


class DocumentError(ValueError):
    """A file could not be read.  ``str(exc)`` is a plain-language message for users."""


class UnsupportedDocument(DocumentError):
    pass


class ScannedPdfError(DocumentError):
    pass


@dataclass
class ExtractedDocument:
    text: str
    kind: str  # "txt" | "docx" | "pdf"
    pages: int | None = None
    warnings: list[str] = field(default_factory=list)
    encoding: str | None = None


_ARCHIVE_MESSAGE = "This file is a compressed archive. Please unzip it and add the documents inside."
_EXECUTABLE_MAGIC = (
    b"MZ",  # Windows PE
    b"\x7fELF",  # Linux
    b"\xfe\xed\xfa\xce",  # Mach-O 32
    b"\xfe\xed\xfa\xcf",  # Mach-O 64
    b"\xce\xfa\xed\xfe",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",  # Mach-O fat / Java class
    b"#!",  # script with shebang
)
_ARCHIVE_MAGIC = (
    b"\x1f\x8b",  # gzip
    b"7z\xbc\xaf\x27\x1c",
    b"Rar!\x1a\x07",
    b"BZh",
    b"\xfd7zXZ\x00",
)


def detect_kind(data: bytes, filename: str | None = None) -> str:
    """Return ``"txt"``, ``"docx"``, or ``"pdf"`` based on the file's content.

    Raises ``UnsupportedDocument`` for executables, archives, other binary
    formats, and content that does not match the file extension.
    """
    ext = Path(filename).suffix.lower() if filename else ""
    if ext and ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedDocument(f"Studio can read .txt, .docx and .pdf files. “{filename}” is a different type.")
    if any(data.startswith(m) for m in _EXECUTABLE_MAGIC):
        raise UnsupportedDocument("This file looks like a program, not a document, so it was not opened.")
    if any(data.startswith(m) for m in _ARCHIVE_MAGIC):
        raise UnsupportedDocument(_ARCHIVE_MESSAGE)

    if data.startswith(b"%PDF-"):
        kind = "pdf"
    elif data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = set(zf.namelist())
        except zipfile.BadZipFile as exc:
            raise UnsupportedDocument("This file seems to be damaged and could not be opened.") from exc
        if "word/document.xml" not in names:
            raise UnsupportedDocument(
                "This file is a compressed archive. Please unzip it and add the documents inside."
            )
        kind = "docx"
    else:
        sample = data[:8192]
        if b"\x00" in sample and not (sample.startswith((b"\xff\xfe", b"\xfe\xff"))):
            raise UnsupportedDocument("This file isn't a text document Studio can read.")
        kind = "txt"

    if ext and ext != f".{kind}":
        raise UnsupportedDocument(
            f"“{filename}” says it is a {ext} file, but its contents look like a .{kind} file. "
            "Please check the file and try again."
        )
    return kind


def _decode_text(data: bytes) -> tuple[str, str, list[str]]:
    warnings: list[str] = []
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace"), "utf-8-sig", warnings
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace"), "utf-16", warnings
    try:
        return data.decode("utf-8"), "utf-8", warnings
    except UnicodeDecodeError:
        pass
    try:
        text = data.decode("cp1252")
        warnings.append("This file was not saved as UTF-8; it was read using the Windows (cp1252) encoding.")
        return text, "cp1252", warnings
    except UnicodeDecodeError:
        warnings.append("Some characters in this file could not be read and were replaced.")
        return data.decode("latin-1"), "latin-1", warnings


# --- DOCX -------------------------------------------------------------------


def _require_docx() -> Any:
    try:
        import docx
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise DocumentError("Reading Word files needs the optional extra: pip install 'phi-guard[studio]'") from exc
    return docx


def _docx_paragraphs(document: Any) -> Iterator[Any]:
    """Yield every paragraph in reading order: headers, body (incl. tables), footers.

    Headers and footers are included on purpose: patient names often appear
    in letterhead and page footers.
    """
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    seen_parts: set[int] = set()

    def header_footer(attr: str) -> Iterator[Any]:
        for section in document.sections:
            part = getattr(section, attr)
            if part.is_linked_to_previous or id(part._element) in seen_parts:
                continue
            seen_parts.add(id(part._element))
            yield from part.paragraphs
            for table in part.tables:
                yield from _table_paragraphs(table)

    def _table_paragraphs(table: Any) -> Iterator[Any]:
        for row in table.rows:
            seen_cells: set[int] = set()
            for cell in row.cells:
                if id(cell._tc) in seen_cells:  # merged cells repeat
                    continue
                seen_cells.add(id(cell._tc))
                yield from cell.paragraphs
                for inner in cell.tables:
                    yield from _table_paragraphs(inner)

    yield from header_footer("header")
    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            yield Paragraph(child, document._body)
        elif tag == "tbl":
            yield from _table_paragraphs(Table(child, document._body))
    yield from header_footer("footer")


def _extract_docx(data: bytes) -> ExtractedDocument:
    docx = _require_docx()
    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise DocumentError("We couldn't open this Word file. It may be damaged or password-protected.") from exc
    text = "\n".join(p.text for p in _docx_paragraphs(document))
    return ExtractedDocument(text=text, kind="docx")


def docx_with_replacements(data: bytes, replace: Callable[[str], str] | list[tuple[int, int, str]]) -> bytes:
    """Return a copy of a .docx with text replaced.

    ``replace`` is either a function applied to each paragraph's text, or a
    list of ``(start, end, replacement)`` spans in the coordinates of the
    text returned by ``extract_text`` for the same file.  A span that
    crosses a paragraph break is replaced in the first paragraph and the
    remainder is removed from the following ones.
    """
    docx = _require_docx()
    document = docx.Document(io.BytesIO(data))
    paragraphs = list(_docx_paragraphs(document))
    offset = 0
    spans = sorted(replace, key=lambda s: s[0]) if isinstance(replace, list) else None
    for para in paragraphs:
        original = para.text
        p_start, p_end = offset, offset + len(original)
        offset = p_end + 1  # the "\n" between paragraphs
        if spans is None:
            assert callable(replace)
            new = replace(original)
        else:
            pieces: list[str] = []
            cursor = p_start
            for s, e, token in spans:
                if e <= p_start or s >= p_end:
                    continue
                lo, hi = max(s, p_start), min(e, p_end)
                pieces.append(original[cursor - p_start : lo - p_start])
                if s >= p_start:
                    pieces.append(token)
                cursor = hi
            pieces.append(original[cursor - p_start :])
            new = "".join(pieces)
        if new != original:
            _set_paragraph_text(para, new)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def _set_paragraph_text(para: Any, text: str) -> None:
    runs = para.runs
    if not runs:
        para.add_run(text)
        return
    runs[0].text = text
    for run in runs[1:]:
        run._element.getparent().remove(run._element)
    # Hyperlinks and fields hold their own runs; clear any text left in them.
    keep = list(runs[0]._element.iter())
    for node in list(para._p.iter()):
        if node.tag.rsplit("}", 1)[-1] == "t" and not any(node is k for k in keep):
            node.text = ""


# --- PDF --------------------------------------------------------------------


def _extract_pdf(data: bytes) -> ExtractedDocument:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise DocumentError("Reading PDF files needs the optional extra: pip install 'phi-guard[studio]'") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentError("This PDF is password-protected. Please remove the password and try again.")
        pages = [page.extract_text() or "" for page in reader.pages]
    except DocumentError:
        raise
    except (PdfReadError, ValueError, KeyError, OSError) as exc:
        raise DocumentError("We couldn't open this PDF. It may be damaged.") from exc
    warnings = [
        f"Page {i} has no readable text (it may be a scanned image) and was skipped."
        for i, page_text in enumerate(pages, 1)
        if not page_text.strip()
    ]
    if not any(p.strip() for p in pages):
        raise ScannedPdfError(
            "We couldn't read this file. It looks like a scanned image, which has no text inside. "
            "Try copying the text instead, or use the original typed document."
        )
    return ExtractedDocument(text="\n\n".join(pages), kind="pdf", pages=len(pages), warnings=warnings)


# --- public entry point -------------------------------------------------------


def extract_text(source: str | Path | bytes, filename: str | None = None) -> ExtractedDocument:
    """Extract text from a file path or from raw bytes.

    ``filename`` is used for the extension check when ``source`` is bytes.
    """
    if isinstance(source, bytes):
        data = source
    else:
        path = Path(source)
        data = path.read_bytes()
        filename = filename or path.name
    kind = detect_kind(data, filename)
    if kind == "pdf":
        return _extract_pdf(data)
    if kind == "docx":
        return _extract_docx(data)
    text, encoding, warnings = _decode_text(data)
    return ExtractedDocument(text=text, kind="txt", warnings=warnings, encoding=encoding)
