"""Render synthetic documents as page images, optionally degraded to look like a fax.

Used by the OCR benchmark and tests.  Everything is synthetic and seeded.

Quality levels:

* ``scan``: a clean office scan (300 dpi, greyscale, no noise).
* ``fax``: a standard-resolution fax: about 200 x 100 dpi (every other scan
  line dropped), pure black and white, a slight skew, light blur before
  thresholding, and speckle noise.
* ``bad_fax``: like ``fax`` with more skew, noise and blur, the worst case
  a clinic still receives.
"""

from __future__ import annotations

import math
import random
import textwrap
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFilter, ImageFont

__all__ = ["LEVELS", "Layout", "render_page", "render_pages", "render_with_layout"]


@dataclass(frozen=True)
class Level:
    dpi: int
    drop_lines: bool  # standard fax: half vertical resolution
    skew_deg: float
    blur: float
    threshold: int | None  # None = keep greyscale
    speckle: float  # fraction of pixels flipped


LEVELS: dict[str, Level] = {
    "scan": Level(dpi=300, drop_lines=False, skew_deg=0.0, blur=0.0, threshold=None, speckle=0.0),
    "fax": Level(dpi=200, drop_lines=True, skew_deg=0.8, blur=0.6, threshold=150, speckle=0.002),
    "bad_fax": Level(dpi=200, drop_lines=True, skew_deg=1.8, blur=0.9, threshold=135, speckle=0.006),
}

PAGE_W_IN, PAGE_H_IN, MARGIN_IN = 8.5, 11.0, 0.75
FONT_PT = 11


def _font(px: int, path: str | None = None) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # By default use the scalable font Pillow ships, so output is identical on every machine.
    # It has no accented letters; pass a font file (e.g. DejaVu Sans) for French text.
    return ImageFont.truetype(path, px) if path else ImageFont.load_default(size=px)


def _wrap(text: str, width: int) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        lines.extend(textwrap.wrap(raw, width=width, break_long_words=False, break_on_hyphens=False) or [""])
    return lines


@dataclass
class Layout:
    """Where each line of the source text was drawn, so true pixel boxes of any span can be computed."""

    size: tuple[int, int]
    # (page, start offset in source text, line text, x, y, top, bottom) for every drawn line
    lines: list[tuple[int, int, str, int, int, int, int]] = field(default_factory=list)
    angles: list[float] = field(default_factory=list)  # skew applied to each page, degrees
    font: object = None

    def span_boxes(self, start: int, end: int) -> list[tuple[int, tuple[float, float, float, float]]]:
        """Pixel boxes (page, (left, top, right, bottom)) covering source-text span [start, end) after skew."""
        out = []
        for page, line_start, line, x, _y, top, bottom in self.lines:
            lo, hi = max(start, line_start), min(end, line_start + len(line))
            if lo >= hi:
                continue
            x0 = x + self.font.getlength(line[: lo - line_start])  # type: ignore[attr-defined]
            x1 = x + self.font.getlength(line[: hi - line_start])  # type: ignore[attr-defined]
            out.append((page, _rotate_box((x0, top, x1, bottom), self.angles[page], self.size)))
        return out


def _rotate_box(box: tuple[float, float, float, float], angle: float, size: tuple[int, int]):
    """Bounding box of ``box`` after Pillow's ``rotate(angle)`` about the image centre (counter-clockwise)."""
    cx, cy = size[0] / 2, size[1] / 2
    t = math.radians(angle)
    xs, ys = [], []
    for px, py in ((box[0], box[1]), (box[2], box[1]), (box[0], box[3]), (box[2], box[3])):
        dx, dy = px - cx, py - cy
        xs.append(cx + dx * math.cos(t) + dy * math.sin(t))
        ys.append(cy - dx * math.sin(t) + dy * math.cos(t))
    return (min(xs), min(ys), max(xs), max(ys))


def render_with_layout(
    text: str, level: str = "scan", seed: int = 0, font: str | None = None
) -> tuple[list[Image.Image], Layout]:
    """Render ``text`` onto letter-size pages and record where every line was drawn."""
    q = LEVELS[level]
    rng = random.Random(seed)
    w, h = int(PAGE_W_IN * q.dpi), int(PAGE_H_IN * q.dpi)
    margin = int(MARGIN_IN * q.dpi)
    font_px = round(FONT_PT / 72 * q.dpi)
    face = _font(font_px, font)
    line_h = int(font_px * 1.45)
    char_w = face.getlength("abcdefghijklmnopqrstuvwxyz") / 26
    lines = _wrap(text, max(20, int((w - 2 * margin) / char_w)))
    per_page = max(1, (h - 2 * margin) // line_h)
    layout = Layout(size=(w, h), font=face)

    # Find each wrapped line's offset in the source text (wrapping only drops whitespace).
    offsets, cursor = [], 0
    for line in lines:
        pos = text.find(line, cursor) if line else cursor
        pos = cursor if pos < 0 else pos
        offsets.append(pos)
        cursor = pos + len(line)

    pages: list[Image.Image] = []
    for page_no, start in enumerate(range(0, len(lines), per_page)):
        img = Image.new("L", (w, h), 255)
        draw = ImageDraw.Draw(img)
        y = margin
        for line, off in zip(lines[start : start + per_page], offsets[start : start + per_page], strict=True):
            draw.text((margin, y), line, fill=0, font=face)
            if line:
                _l, top, _r, bottom = draw.textbbox((margin, y), line, font=face)
                layout.lines.append((page_no, off, line, margin, y, top, bottom))
            y += line_h
        degraded, angle = _degrade(img, q, rng)
        pages.append(degraded)
        layout.angles.append(angle)
    return pages, layout


def render_pages(text: str, level: str = "scan", seed: int = 0, font: str | None = None) -> list[Image.Image]:
    """Render ``text`` onto letter-size pages at the given quality level."""
    return render_with_layout(text, level, seed, font)[0]


def render_page(text: str, level: str = "scan", seed: int = 0, font: str | None = None) -> Image.Image:
    return render_pages(text, level, seed, font)[0]


def _degrade(img: Image.Image, q: Level, rng: random.Random) -> tuple[Image.Image, float]:
    angle = 0.0
    if q.skew_deg:
        angle = rng.uniform(-q.skew_deg, q.skew_deg)
        img = img.rotate(angle, resample=Image.BICUBIC, fillcolor=255, expand=False)
    if q.drop_lines:
        w, h = img.size
        img = img.resize((w, h // 2), Image.BILINEAR).resize((w, h), Image.NEAREST)
    if q.blur:
        img = img.filter(ImageFilter.GaussianBlur(q.blur))
    if q.threshold is not None:
        img = img.point(lambda v: 255 if v > q.threshold else 0)
    if q.speckle:
        px = img.load()
        w, h = img.size
        for _ in range(int(w * h * q.speckle)):
            x, y = rng.randrange(w), rng.randrange(h)
            px[x, y] = 0 if px[x, y] else 255
    return (img.convert("1") if q.threshold is not None else img), angle
