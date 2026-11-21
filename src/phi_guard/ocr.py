"""Read text from scanned documents and fax images with Tesseract OCR.

Referrals often arrive by fax or as scanned PDFs: pictures of pages with no
text inside.  This module turns those pictures into text (optical character
recognition) so the normal detectors can run, and records where each word
sits on the page so a **redacted copy of the scan itself** can be produced
with black boxes over patient details.

Design choices (see DECISIONS.md D39 to D45):

* **Tesseract** (open source, Apache 2.0) does the recognition.  It was more
  accurate and faster than the pip-only alternative tested, and reads French.
* Tesseract runs as a **separate process fed through pipes**: the image goes
  in on stdin and text comes out on stdout.  Nothing is written to a
  temporary file (the popular ``pytesseract`` wrapper writes every image to
  disk, which would put patient documents on disk).  A separate process also
  means a malformed image cannot crash Studio, and each page has a time limit.
* Pages are cleaned with a 3x3 **median filter** (removes fax speckle) before
  recognition, and read with Tesseract's automatic page layout.  Both choices
  were made on the benchmark's development split only.
* Image size and page count are capped to stop "decompression bomb" files.

The core library stays dependency-free: Pillow and pypdfium2 are imported
only when a scan is actually read (``[ocr]`` or ``[studio]`` extra), and the
Tesseract program must be installed separately.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import warnings
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = [
    "LOW_CONFIDENCE",
    "MAX_OCR_PAGES",
    "OcrError",
    "OcrResult",
    "OcrUnavailable",
    "OcrWord",
    "find_tesseract",
    "images_to_pdf",
    "is_available",
    "load_images",
    "ocr_images",
    "pdf_page_images",
    "redact_images",
    "tesseract_info",
]

#: Words Tesseract is less than 60% sure about are counted as "low confidence".
LOW_CONFIDENCE = 60
#: Longest document read by OCR (pages).  Longer scans are refused with a clear message.
MAX_OCR_PAGES = 30
#: Pages are rendered or accepted at most at this many pixels (about 300 dpi letter size, with headroom).
MAX_PAGE_PIXELS = 40_000_000
RENDER_DPI = 300
PAGE_TIMEOUT_S = 90
PSM = "3"  # automatic page layout: copes with letterheads and columns in real faxes


class OcrError(ValueError):
    """Reading a scan failed.  ``str(exc)`` is a plain-language message."""


class OcrUnavailable(OcrError):
    """The Tesseract program is not installed."""


@dataclass(frozen=True)
class OcrWord:
    text: str
    page: int  # 0-based index into OcrResult.images
    box: tuple[int, int, int, int]  # left, top, right, bottom in page-image pixels
    confidence: float  # 0 to 100
    start: int  # offsets of this word in OcrResult.text
    end: int


@dataclass
class OcrResult:
    text: str
    words: list[OcrWord] = field(default_factory=list)
    images: list[Any] = field(default_factory=list, repr=False)  # PIL images, kept in memory only

    @property
    def confidence(self) -> float | None:
        """Average word confidence from 0 to 1, or None if no words were read."""
        scores = [w.confidence for w in self.words if w.confidence >= 0]
        return round(sum(scores) / len(scores) / 100, 3) if scores else None

    @property
    def low_confidence_words(self) -> int:
        return sum(1 for w in self.words if 0 <= w.confidence < LOW_CONFIDENCE)


# --- finding and describing Tesseract -------------------------------------------


def _candidates() -> Iterable[str]:
    env = os.environ.get("PHI_GUARD_TESSERACT")
    if env:
        yield env
    exe = "tesseract.exe" if os.name == "nt" else "tesseract"
    if getattr(sys, "frozen", False):  # PyInstaller build: look next to the app first
        yield str(Path(sys.executable).parent / "tesseract" / exe)
    found = shutil.which("tesseract")
    if found:
        yield found
    if os.name == "nt":
        for base in (os.environ.get("PROGRAMFILES", r"C:\Program Files"), os.environ.get("LOCALAPPDATA", "")):
            if base:
                yield str(Path(base) / "Tesseract-OCR" / exe)
                yield str(Path(base) / "Programs" / "Tesseract-OCR" / exe)
    else:
        yield from ("/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract", "/usr/bin/tesseract")


def find_tesseract() -> str | None:
    """Path to the Tesseract program, or None.  ``PHI_GUARD_TESSERACT`` overrides the search."""
    for path in _candidates():
        if path and Path(path).is_file() and os.access(path, os.X_OK):
            return path
    return None


@lru_cache(maxsize=4)
def _info(path: str) -> dict[str, Any]:
    try:
        version = subprocess.run([path, "--version"], capture_output=True, timeout=15, check=False)
        langs = subprocess.run([path, "--list-langs"], capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "version": None, "languages": [], "path": path}
    out = (version.stdout + version.stderr).decode(errors="replace")
    match = re.search(r"tesseract\s+v?(\d+(?:\.\d+)+)", out, re.IGNORECASE)
    lines = (langs.stdout + langs.stderr).decode(errors="replace").splitlines()
    start = next((i + 1 for i, line in enumerate(lines) if "list of available languages" in line.lower()), len(lines))
    languages = [line.strip() for line in lines[start:] if line.strip() and line.strip() != "osd"]
    return {"available": True, "version": match.group(1) if match else None, "languages": languages, "path": path}


def tesseract_info() -> dict[str, Any]:
    """``{"available", "version", "languages", "path"}`` for the installed Tesseract."""
    path = find_tesseract()
    if path is None:
        return {"available": False, "version": None, "languages": [], "path": None}
    return dict(_info(path))


def is_available() -> bool:
    return bool(tesseract_info()["available"])


# --- images in -------------------------------------------------------------------


def _pillow() -> Any:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise OcrUnavailable("Reading scans needs the optional extra: pip install 'phi-guard[ocr]'") from exc
    Image.MAX_IMAGE_PIXELS = MAX_PAGE_PIXELS
    return Image


def _check_pages(n: int) -> None:
    if n > MAX_OCR_PAGES:
        raise OcrError(
            f"This scan has {n} pages. Studio reads up to {MAX_OCR_PAGES} scanned pages at a time; "
            "please split the document."
        )


def load_images(data: bytes) -> list[Any]:
    """Open a PNG, JPEG or (multi-page) TIFF fax image from memory."""
    Image = _pillow()
    from PIL import ImageSequence

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            img = Image.open(io.BytesIO(data))
            frames = [frame.copy() for frame in ImageSequence.Iterator(img)]
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise OcrError("This image is too large to read safely.") from exc
    except (OSError, ValueError, SyntaxError) as exc:
        raise OcrError("We couldn't open this image. It may be damaged.") from exc
    _check_pages(len(frames))
    return [_normalize_dpi(f) for f in frames]


def _normalize_dpi(img: Any) -> Any:
    """Faxes are often 204 x 98 dpi: stretch to square pixels so letters aren't squashed."""
    dpi = img.info.get("dpi")
    if isinstance(dpi, tuple) and len(dpi) == 2 and dpi[0] and dpi[1]:
        x, y = float(dpi[0]), float(dpi[1])
        if y > 0 and x / y > 1.5:
            Image = _pillow()
            img = img.resize((img.width, round(img.height * x / y)), Image.NEAREST)
    return img


def pdf_page_images(data: bytes, pages: Sequence[int]) -> list[Any]:
    """Render the given (0-based) PDF pages to images in memory with PDFium."""
    _pillow()
    _check_pages(len(pages))
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise OcrUnavailable("Reading scanned PDFs needs the optional extra: pip install 'phi-guard[ocr]'") from exc
    try:
        pdf = pdfium.PdfDocument(data)
    except Exception as exc:  # pypdfium2 raises its own error types
        raise OcrError("We couldn't open this PDF. It may be damaged.") from exc
    images = []
    try:
        for i in pages:
            page = pdf[i]
            w_pt, h_pt = page.get_size()
            scale = RENDER_DPI / 72
            if (w_pt * scale) * (h_pt * scale) > MAX_PAGE_PIXELS:
                scale = (MAX_PAGE_PIXELS / (w_pt * h_pt)) ** 0.5
            images.append(page.render(scale=scale, grayscale=True).to_pil())
            page.close()
    finally:
        pdf.close()
    return images


# --- recognition -----------------------------------------------------------------


def _prepare(img: Any) -> Any:
    from PIL import ImageFilter

    return img.convert("L").filter(ImageFilter.MedianFilter(3))


def _run_tesseract(img: Any, lang: str, path: str) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    env = {**os.environ, "OMP_THREAD_LIMIT": "2"}
    try:
        proc = subprocess.run(
            [path, "stdin", "stdout", "-l", lang, "--psm", PSM, "tsv"],
            input=buf.getvalue(),
            capture_output=True,
            timeout=PAGE_TIMEOUT_S,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise OcrError("Reading this scan took too long. Try a clearer copy or fewer pages.") from exc
    except OSError as exc:
        raise OcrUnavailable("The text-recognition program (Tesseract) could not be started.") from exc
    if proc.returncode != 0:
        raise OcrError("We couldn't read text from this scan.")
    return proc.stdout.decode("utf-8", errors="replace")


def ocr_images(images: Sequence[Any], lang: str = "eng") -> OcrResult:
    """Recognize text on page images.  Pages are joined with a blank line, like text PDFs."""
    path = find_tesseract()
    if path is None:
        raise OcrUnavailable(
            "Studio can read scanned documents once its text-recognition add-on (Tesseract) is installed. "
            "Ask your IT provider to install it, or copy the text instead."
        )
    if not re.fullmatch(r"[a-z]{3}(?:\+[a-z]{3})*", lang):
        raise ValueError(f"invalid OCR language {lang!r}")
    _check_pages(len(images))
    text_parts: list[str] = []
    words: list[OcrWord] = []
    offset = 0
    for page_index, img in enumerate(images):
        if page_index:
            text_parts.append("\n\n")
            offset += 2
        page_text, page_words = _parse_tsv(_run_tesseract(_prepare(img), lang, path), page_index, offset)
        text_parts.append(page_text)
        words.extend(page_words)
        offset += len(page_text)
    return OcrResult("".join(text_parts), words, list(images))


def _parse_tsv(tsv: str, page: int, base: int) -> tuple[str, list[OcrWord]]:
    """Turn Tesseract TSV into page text, keeping each word's offsets and box."""
    out: list[str] = []
    words: list[OcrWord] = []
    pos = 0
    last_line: tuple[str, ...] | None = None
    last_block: tuple[str, ...] | None = None
    for row in tsv.splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or cols[0] != "5":  # level 5 = a word
            continue
        text = cols[11].strip()
        if not text:
            continue
        block, line = (cols[2], cols[3]), (cols[2], cols[3], cols[4])
        if last_line is None:
            sep = ""
        elif block != last_block:
            sep = "\n\n"
        elif line != last_line:
            sep = "\n"
        else:
            sep = " "
        out.append(sep)
        pos += len(sep)
        left, top, width, height = (int(c) for c in cols[6:10])
        try:
            conf = float(cols[10])
        except ValueError:
            conf = -1.0
        words.append(
            OcrWord(text, page, (left, top, left + width, top + height), conf, base + pos, base + pos + len(text))
        )
        out.append(text)
        pos += len(text)
        last_line, last_block = line, block
    return "".join(out), words


# --- visual redaction ---------------------------------------------------------------


def redact_images(result: OcrResult, spans: Iterable[tuple[int, int]], pad: int = 3) -> list[Any]:
    """Copies of the page images with solid black boxes over every word touched by a span.

    Whole words are covered even if a span touches only part of one (when in
    doubt, black it out).  The words of one detail that sit on the same line are
    merged into a single box, so the box doesn't reveal how many words the
    detail had or how long each one was.
    """
    from PIL import ImageDraw

    pages = [img.convert("L").copy() for img in result.images]
    draws = [ImageDraw.Draw(p) for p in pages]
    for s, e in sorted(spans):
        line: list[OcrWord] = []
        for w in (w for w in result.words if s < w.end and w.start < e):
            if line and (w.page != line[-1].page or not _same_line(w, line[-1])):
                _draw_box(draws[line[0].page], line, pad)
                line = []
            line.append(w)
        if line:
            _draw_box(draws[line[0].page], line, pad)
    return pages


def _same_line(a: OcrWord, b: OcrWord) -> bool:
    overlap = min(a.box[3], b.box[3]) - max(a.box[1], b.box[1])
    return overlap > 0.5 * min(a.box[3] - a.box[1], b.box[3] - b.box[1])


def _draw_box(draw: Any, words: list[OcrWord], pad: int) -> None:
    left = min(w.box[0] for w in words) - pad
    top = min(w.box[1] for w in words) - pad
    right = max(w.box[2] for w in words) + pad
    bottom = max(w.box[3] for w in words) + pad
    draw.rectangle((left, top, right, bottom), fill=0)


def images_to_pdf(images: Sequence[Any], dpi: int = RENDER_DPI) -> bytes:
    """An image-only PDF (no text layer), so nothing hidden survives under the black boxes."""
    if not images:
        raise ValueError("no pages")
    buf = io.BytesIO()
    first, *rest = [img.convert("L") for img in images]
    first.save(buf, "PDF", save_all=True, append_images=rest, resolution=dpi)
    return buf.getvalue()
