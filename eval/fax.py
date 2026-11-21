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

import random
import textwrap
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFilter, ImageFont

__all__ = ["LEVELS", "render_page", "render_pages"]


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


def render_pages(text: str, level: str = "scan", seed: int = 0, font: str | None = None) -> list[Image.Image]:
    """Render ``text`` onto letter-size pages at the given quality level."""
    q = LEVELS[level]
    rng = random.Random(seed)
    w, h = int(PAGE_W_IN * q.dpi), int(PAGE_H_IN * q.dpi)
    margin = int(MARGIN_IN * q.dpi)
    font_px = round(FONT_PT / 72 * q.dpi)
    font = _font(font_px, font)
    line_h = int(font_px * 1.45)
    char_w = font.getlength("abcdefghijklmnopqrstuvwxyz") / 26
    lines = _wrap(text, max(20, int((w - 2 * margin) / char_w)))
    per_page = max(1, (h - 2 * margin) // line_h)

    pages: list[Image.Image] = []
    for start in range(0, len(lines), per_page):
        img = Image.new("L", (w, h), 255)
        draw = ImageDraw.Draw(img)
        y = margin
        for line in lines[start : start + per_page]:
            draw.text((margin, y), line, fill=0, font=font)
            y += line_h
        pages.append(_degrade(img, q, rng))
    return pages


def render_page(text: str, level: str = "scan", seed: int = 0, font: str | None = None) -> Image.Image:
    return render_pages(text, level, seed, font)[0]


def _degrade(img: Image.Image, q: Level, rng: random.Random) -> Image.Image:
    if q.skew_deg:
        img = img.rotate(rng.uniform(-q.skew_deg, q.skew_deg), resample=Image.BICUBIC, fillcolor=255, expand=False)
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
    return img.convert("1") if q.threshold is not None else img
