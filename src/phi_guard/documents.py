"""Extract text from .txt, .docx, .pdf and scanned images; write redacted copies.

Scanned PDFs, faxes and photos (``.png``, ``.jpg``, ``.tif``) are read with
OCR (``ocr.py``).  A PDF page that has no text layer is read with OCR too, so
a typed cover sheet followed by faxed pages works.

The core library stays dependency-free: ``python-docx``, ``pypdf``, Pillow and
``pypdfium2`` are imported only when such a file is actually opened (install
the ``[studio]``, ``[docs]`` or ``[ocr]`` extra).

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
    "redacted_scan_pdf",
]

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tif", ".tiff")
SUPPORTED_EXTENSIONS = (".txt", ".docx", ".pdf", *IMAGE_EXTENSIONS)
_KIND_EXTENSIONS = {"txt": (".txt",), "docx": (".docx",), "pdf": (".pdf",), "image": IMAGE_EXTENSIONS}
_IMAGE_MAGIC = (
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",  # JPEG
    b"II*\x00",  # TIFF, little-endian
    b"MM\x00*",  # TIFF, big-endian
)


class DocumentError(ValueError):
    """A file could not be read.  ``str(exc)`` is a plain-language message for users."""


class UnsupportedDocument(DocumentError):
    pass


class ScannedPdfError(DocumentError):
    pass


@dataclass
class ExtractedDocument:
    text: str
    kind: str  # "txt" | "docx" | "pdf" | "image"
    pages: int | None = None
    warnings: list[str] = field(default_factory=list)
    encoding: str | None = None
    #: 1-based numbers of pages whose text came from OCR.
    ocr_pages: list[int] = field(default_factory=list)
    ocr_confidence: float | None = None  # average word confidence, 0 to 1
    low_confidence_words: int = 0
    #: Word positions and page images, kept only when *every* page was read by OCR,
    #: so a redacted copy of the scan can be produced.  In memory only.
    ocr: Any = field(default=None, repr=False)

    @property
    def used_ocr(self) -> bool:
        return bool(self.ocr_pages)


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
        raise UnsupportedDocument(
            f"Studio can read .txt, .docx and .pdf files and scanned images (.png, .jpg, .tif). "
            f"“{filename}” is a different type."
        )
    if any(data.startswith(m) for m in _EXECUTABLE_MAGIC):
        raise UnsupportedDocument("This file looks like a program, not a document, so it was not opened.")
    if any(data.startswith(m) for m in _ARCHIVE_MAGIC):
        raise UnsupportedDocument(_ARCHIVE_MESSAGE)

    if data.startswith(b"%PDF-"):
        kind = "pdf"
    elif data.startswith(_IMAGE_MAGIC):
        kind = "image"
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

    if ext and ext not in _KIND_EXTENSIONS[kind]:
        described = "an image" if kind == "image" else f"a .{kind} file"
        raise UnsupportedDocument(
            f"“{filename}” says it is a {ext} file, but its contents look like {described}. "
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


def _extract_pdf(data: bytes, ocr: bool, ocr_lang: str) -> ExtractedDocument:
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

    empty = [i for i, t in enumerate(pages) if not t.strip()]
    doc = ExtractedDocument(text="", kind="pdf", pages=len(pages))
    if empty and ocr:
        from . import ocr as ocr_mod

        if ocr_mod.is_available():
            try:
                images = ocr_mod.pdf_page_images(data, empty)
                results = [ocr_mod.ocr_images([img], ocr_lang) for img in images]
            except ocr_mod.OcrError as exc:
                raise DocumentError(str(exc)) from exc
            for i, res in zip(empty, results, strict=True):
                if res.text.strip():
                    pages[i] = res.text
                    doc.ocr_pages.append(i + 1)
            _summarize_ocr(doc, [r for r in results if r.text.strip()])
            if len(doc.ocr_pages) == len(pages):  # a fully scanned PDF: keep word boxes for a redacted scan
                doc.ocr = _merge_results(results)
        elif len(empty) == len(pages):
            raise ScannedPdfError(
                "This PDF is a scanned image, which has no text inside. Studio can read scans once its "
                "text-recognition add-on (Tesseract) is installed: ask your IT provider. Or copy the text instead."
            )
    elif empty and len(empty) == len(pages):
        raise ScannedPdfError(
            "This PDF is a scanned image. Reading scanned documents is turned off in Settings; turn it on to read it."
        )
    doc.warnings += [
        f"Page {i} has no readable text and was skipped."
        for i, page_text in enumerate(pages, 1)
        if not page_text.strip()
    ]
    if not any(p.strip() for p in pages):
        raise ScannedPdfError(
            "We couldn't find any readable text in this file. If it is a scan, it may be too faint or blurry: "
            "try a clearer copy, or type the text instead."
        )
    doc.text = "\n\n".join(pages)
    return doc


def _merge_results(results: list[Any]) -> Any:
    """Join single-page OCR results the same way pages are joined in the document text."""
    from .ocr import OcrResult, OcrWord

    merged = OcrResult("")
    offset = 0
    for page, res in enumerate(results):
        if page:
            offset += 2  # "\n\n" between pages
        merged.words += [
            OcrWord(w.text, page, w.box, w.confidence, w.start + offset, w.end + offset) for w in res.words
        ]
        merged.images += res.images
        offset += len(res.text)
    merged.text = "\n\n".join(r.text for r in results)
    return merged


def _summarize_ocr(doc: ExtractedDocument, results: list[Any]) -> None:
    words = [w for r in results for w in r.words if w.confidence >= 0]
    if words:
        doc.ocr_confidence = round(sum(w.confidence for w in words) / len(words) / 100, 3)
    doc.low_confidence_words = sum(r.low_confidence_words for r in results)
    if doc.ocr_pages:
        pct = f" (average confidence {doc.ocr_confidence:.0%})" if doc.ocr_confidence is not None else ""
        where = (
            "This text was" if len(doc.ocr_pages) == doc.pages else f"Page(s) {', '.join(map(str, doc.ocr_pages))} were"
        )
        doc.warnings.append(
            f"{where} read from a scanned image{pct}. Check names and numbers against the original before sharing."
        )


def _extract_image(data: bytes, ocr: bool, ocr_lang: str) -> ExtractedDocument:
    if not ocr:
        raise UnsupportedDocument("Reading scanned images is turned off in Settings.")
    from . import ocr as ocr_mod

    try:
        images = ocr_mod.load_images(data)
        result = ocr_mod.ocr_images(images, ocr_lang)
    except ocr_mod.OcrUnavailable as exc:
        raise ScannedPdfError(str(exc)) from exc
    except ocr_mod.OcrError as exc:
        raise DocumentError(str(exc)) from exc
    if not result.text.strip():
        raise ScannedPdfError(
            "We couldn't find any readable text in this image. It may be too faint or blurry: try a clearer copy."
        )
    doc = ExtractedDocument(
        text=result.text, kind="image", pages=len(images), ocr_pages=list(range(1, len(images) + 1)), ocr=result
    )
    _summarize_ocr(doc, [result])
    return doc


def redacted_scan_pdf(doc: ExtractedDocument, spans: list[tuple[int, int]]) -> bytes:
    """A redacted copy of a fully scanned document: page images with black boxes, no text layer."""
    if doc.ocr is None:
        raise DocumentError("A redacted copy of the scan is only available for fully scanned documents.")
    from .ocr import images_to_pdf, redact_images

    return images_to_pdf(redact_images(doc.ocr, spans))


# --- public entry point -------------------------------------------------------


def extract_text(
    source: str | Path | bytes,
    filename: str | None = None,
    *,
    ocr: bool = True,
    ocr_lang: str = "eng",
) -> ExtractedDocument:
    """Extract text from a file path or from raw bytes.

    ``filename`` is used for the extension check when ``source`` is bytes.
    ``ocr`` turns reading of scanned pages and images on or off; ``ocr_lang``
    is a Tesseract language code such as ``"eng"`` or ``"eng+fra"``.
    """
    if isinstance(source, bytes):
        data = source
    else:
        path = Path(source)
        data = path.read_bytes()
        filename = filename or path.name
    kind = detect_kind(data, filename)
    if kind == "pdf":
        return _extract_pdf(data, ocr, ocr_lang)
    if kind == "image":
        return _extract_image(data, ocr, ocr_lang)
    if kind == "docx":
        return _extract_docx(data)
    text, encoding, warnings = _decode_text(data)
    return ExtractedDocument(text=text, kind="txt", warnings=warnings, encoding=encoding)
