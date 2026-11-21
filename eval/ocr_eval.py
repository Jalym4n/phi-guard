"""Benchmark: how well redaction works on scanned and faxed documents.

Each test-split document is rendered as page images at three quality levels
(``eval/fax.py``): a clean office scan, a standard fax, and a bad fax.  The
images go through the same OCR pipeline Studio uses, then phi-guard's default
redaction.  We then ask the privacy officer's question: **does any patient
detail still appear in the output?**

Survival is measured on the redacted output text, ignoring case, spaces and
punctuation:

* A detail survives if it still appears **exactly or nearly** (OCR misreads
  such as ``Whitfie1d`` still reveal the name): any stretch of the output
  within an edit distance of len/6 counts as a survival.
* Names are checked **word by word**: if the first name is removed but the
  surname survives, the name leaked.

The same measurement on the original (typed) text gives the baseline, so the
difference is the cost of reading from a scan.

A second check covers the **redacted copy of the scan** (black boxes).  The
renderer records exactly where each character was drawn (including the fax
skew), so for every labelled detail we measure how much of its true area the
black boxes cover.  A detail counts as hidden only if at least 98% of its ink (dark pixels) is
under a black box.  (Re-reading the redacted scan with OCR would be misleading: a detail
the OCR misread, and so did not box, tends to be misread again, while a person
could still read it.)

The OCR pipeline (Tesseract, 3x3 median filter, automatic page layout) was
chosen on dev documents only and frozen in a commit before this ran.

Usage::

    python -m eval.ocr_eval              # 150 test documents (about 5 minutes)
    python -m eval.ocr_eval --docs 20    # quicker
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from phi_guard import ocr
from phi_guard.detectors import ALL_KINDS
from phi_guard.ocr import OcrResult, ocr_images, redact_images
from phi_guard.redactor import Redactor

from .fax import Layout, render_with_layout
from .run import DISPLAY, INK, INK_2, LABELS, SERIES, SURFACE, _style, load_jsonl

HERE = Path(__file__).parent
LEVEL_NAMES = {"text": "Typed text (no OCR)", "scan": "Clean office scan", "fax": "Standard fax", "bad_fax": "Bad fax"}


def norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def _edit_distance_within(a: str, b: str, limit: int) -> bool:
    """True if Levenshtein(a, b) <= limit (early exit)."""
    if abs(len(a) - len(b)) > limit:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > limit:
            return False
        prev = cur
    return prev[-1] <= limit


def appears(value: str, haystack: str) -> bool:
    """Does ``value`` (normalized) appear in ``haystack`` (normalized), exactly or nearly?"""
    if not value:
        return False
    if value in haystack:
        return True
    limit = len(value) // 6
    if limit == 0:
        return False
    n = len(value)
    for size in (n - 1, n, n + 1):
        for i in range(0, max(0, len(haystack) - size) + 1):
            if _edit_distance_within(value, haystack[i : i + size], limit):
                return True
    return False


def survives(span: dict[str, Any], output_norm: str) -> bool:
    if span["kind"] == "NAME":
        return any(
            appears(norm(part), output_norm) for part in span["text"].replace(",", " ").split() if len(part) >= 3
        )
    return appears(norm(span["text"]), output_norm)


def char_error_rate(reference: str, hypothesis: str) -> float:
    a, b = " ".join(reference.split()), " ".join(hypothesis.split())
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] / max(1, len(a))


HIDDEN_COVERAGE = 0.98


def box_masks(result: OcrResult, spans: list[tuple[int, int]]) -> list[Any]:
    """Black boxes Studio would draw, on blank pages (black = covered), using the real redaction code."""
    from PIL import Image

    blank = OcrResult(result.text, result.words, [Image.new("L", img.size, 255) for img in result.images])
    return redact_images(blank, spans)


def coverage(masks: list[Any], layout: Layout, gold: dict[str, Any], pages: list[Any]) -> float:
    """Share of a labelled detail's ink (dark pixels where it was drawn) that lies under a black box."""
    ink = hidden = 0
    for page, (x0, y0, x1, y1) in layout.span_boxes(gold["start"], gold["end"]):
        region = (int(x0), int(y0), int(x1 + 1), int(y1 + 1))
        before = pages[page].convert("L").crop(region).tobytes()
        mask = masks[page].crop(region).tobytes()
        for b, m in zip(before, mask, strict=True):
            if b < 128:
                ink += 1
                hidden += m == 0
    return hidden / ink if ink else 1.0


def process(doc: dict[str, Any], level: str, index: int, redactor: Redactor, visual: bool) -> dict[str, Any]:
    gold = [s for s in doc["spans"] if not s.get("ignore")]
    t0 = time.perf_counter()
    layout = None
    if level == "text":
        text, images, result = doc["text"], [], None
    else:
        images, layout = render_with_layout(doc["text"], level, seed=index)
        result = ocr_images(images)
        text = result.text
    seconds = time.perf_counter() - t0
    red = redactor.redact(text, list(ALL_KINDS))
    out_norm = norm(red.text)
    leaked = [s for s in gold if survives(s, out_norm)]
    row: dict[str, Any] = {
        "id": doc["id"],
        "pages": max(1, len(images)),
        "seconds": seconds,
        "cer": char_error_rate(doc["text"], text) if level != "text" else 0.0,
        "gold": [(s["kind"], s["text"]) for s in gold],
        "leaked": [(s["kind"], s["text"]) for s in leaked],
        "confidence": result.confidence if result else None,
    }
    if visual and result is not None and layout is not None:
        masks = box_masks(result, [(f.start, f.end) for f in red.findings])
        row["visual_leaked"] = [
            (s["kind"], s["text"]) for s in gold if coverage(masks, layout, s, images) < HIDDEN_COVERAGE
        ]
    return row


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n_gold = sum(len(r["gold"]) for r in rows)
    n_leak = sum(len(r["leaked"]) for r in rows)
    per_type: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        for kind, _ in r["gold"]:
            per_type[kind][1] += 1
        for kind, _ in r["leaked"]:
            per_type[kind][0] += 1
    pages = sum(r["pages"] for r in rows)
    out = {
        "docs": len(rows),
        "identifiers": n_gold,
        "removed": 1 - n_leak / n_gold if n_gold else 0.0,
        "doc_leakage": sum(bool(r["leaked"]) for r in rows) / len(rows),
        "cer": sum(r["cer"] for r in rows) / len(rows),
        "sec_per_page": sum(r["seconds"] for r in rows) / pages,
        "per_type": {k: 1 - v[0] / v[1] for k, v in per_type.items() if v[1]},
        "confidence": (sum(r["confidence"] for r in rows if r["confidence"]) / len(rows))
        if rows[0]["confidence"]
        else None,
    }
    if all("visual_leaked" in r for r in rows):
        vis = sum(len(r["visual_leaked"]) for r in rows)
        out["visual_removed"] = 1 - vis / n_gold
        out["visual_doc_leakage"] = sum(bool(r["visual_leaked"]) for r in rows) / len(rows)
        # Of the details the text redaction removed, how many did the black boxes also hide?
        removed_in_text = [(r, g) for r in rows for g in r["gold"] if g not in r["leaked"]]
        hidden = sum(1 for r, g in removed_in_text if g not in r["visual_leaked"])
        out["boxes_match_text"] = hidden / len(removed_in_text) if removed_in_text else 0.0
    return out


def chart(summaries: dict[str, dict[str, Any]], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    levels = list(summaries)
    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=150)
    _style(ax)
    ax.grid(axis="y", color="#e4e3df", linewidth=0.8)
    ax.grid(axis="x", visible=False)
    xs = range(len(levels))
    w = 0.38
    removed = [summaries[lv]["removed"] * 100 for lv in levels]
    leak = [summaries[lv]["doc_leakage"] * 100 for lv in levels]
    ax.bar([x - w / 2 for x in xs], removed, width=w - 0.03, color=SERIES[0], label="Identifiers removed")
    ax.bar([x + w / 2 for x in xs], leak, width=w - 0.03, color=SERIES[1], label="Documents with any leak")
    for x, v in zip(xs, removed, strict=True):
        ax.text(x - w / 2, v + 1.5, f"{v:.0f}%", ha="center", fontsize=8, color=INK)
    for x, v in zip(xs, leak, strict=True):
        ax.text(x + w / 2, v + 1.5, f"{v:.0f}%", ha="center", fontsize=8, color=INK)
    ax.set_xticks(list(xs), [LEVEL_NAMES[lv] for lv in levels], color=INK)
    ax.set_ylim(0, 110)
    ax.set_ylabel("% (test split)", color=INK_2)
    ax.set_title("Redaction on scanned and faxed documents", loc="left", fontsize=12, color=INK, pad=24)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def write_report(
    summaries: dict[str, dict[str, Any]], rows: dict[str, list[dict[str, Any]]], info: dict[str, Any]
) -> str:
    pct = lambda x: f"{x * 100:.1f}%"  # noqa: E731
    L = [
        "# Benchmark results: scanned and faxed documents",
        "",
        "> Auto-generated by `python -m eval.ocr_eval`. Main results: [RESULTS.md](RESULTS.md).",
        "",
        f"* {summaries['text']['docs']} test-split documents ({summaries['text']['identifiers']} labelled identifiers), "
        "rendered as page images at three quality levels by `eval/fax.py`.",
        f"* OCR: Tesseract {info.get('version')} (English), 3x3 median filter, automatic page layout. These choices "
        "were made on dev documents only and frozen in a commit before this ran.",
        "* Redaction: phi-guard default configuration, unchanged.",
        "* A detail **survives** if it still appears in the redacted output exactly or nearly (OCR misreads like "
        "`Whitfie1d` still reveal the name); names are checked word by word. Lower survival is better.",
        "",
        "![Redaction on scans](charts/ocr_levels.png)",
        "",
        "| Input | Character error rate | Identifiers removed | Documents with any leak | OCR seconds per page |",
        "|---|---:|---:|---:|---:|",
    ]
    for lv, s in summaries.items():
        L.append(
            f"| {LEVEL_NAMES[lv]} | {pct(s['cer']) if lv != 'text' else '–'} | {pct(s['removed'])} | "
            f"**{pct(s['doc_leakage'])}** | {s['sec_per_page']:.2f} |"
        )
    L += [
        "",
        "## Identifiers removed, by type",
        "",
        "| Type | " + " | ".join(LEVEL_NAMES[lv] for lv in summaries) + " |",
    ]
    L += ["|---|" + "---:|" * len(summaries)]
    for k in LABELS:
        if k in summaries["text"]["per_type"]:
            L.append(
                f"| {DISPLAY[k]} | " + " | ".join(pct(summaries[lv]["per_type"].get(k, 0)) for lv in summaries) + " |"
            )
    if "visual_removed" in summaries.get("fax", {}):
        s = summaries["fax"]
        L += [
            "",
            "## Redacted copy of the scan (black boxes), standard fax",
            "",
            "For every labelled detail we know exactly where it was drawn on the page (including the fax skew), "
            f"and measure how much of its ink (dark pixels) lies under a black box. A detail counts as hidden if at "
            f"least {HIDDEN_COVERAGE:.0%} of its ink is covered.",
            "",
            "| Measure | Result |",
            "|---|---:|",
            f"| Details removed from the redacted text | {pct(s['removed'])} |",
            f"| Details hidden by black boxes on the redacted scan | {pct(s['visual_removed'])} |",
            f"| Of the details removed from the text, also hidden by the black boxes | {pct(s['boxes_match_text'])} |",
            f"| Redacted scans with any detail not fully covered | {pct(s['visual_doc_leakage'])} |",
        ]
    L += ["", "## Examples of details that survived on a standard fax (synthetic)", ""]
    shown: dict[str, int] = defaultdict(int)
    for r in rows.get("fax", []):
        for kind, value in r["leaked"]:
            if shown[kind] < 2:
                shown[kind] += 1
                L.append(f"* `{kind}`: `{value}`")
    disc = HERE / "discussion_ocr.md"
    if disc.exists():
        L += ["", disc.read_text(encoding="utf-8").strip()]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--docs", type=int, default=150)
    ap.add_argument("--split", choices=["dev", "test"], default="test")
    ap.add_argument("--visual-docs", type=int, default=150, help="documents for the black-box coverage check")
    ap.add_argument("--out", type=Path, default=HERE / "RESULTS_OCR.md")
    args = ap.parse_args(argv)
    info = ocr.tesseract_info()
    if not info["available"]:
        print("Tesseract is not installed; skipping the OCR benchmark.")
        return 0
    docs = load_jsonl(HERE / "data" / f"phi_{args.split}.jsonl")[: args.docs]
    redactor = Redactor(key="benchmark")
    summaries: dict[str, dict[str, Any]] = {}
    all_rows: dict[str, list[dict[str, Any]]] = {}
    for level in ("text", "scan", "fax", "bad_fax"):
        print(f"OCR benchmark: {LEVEL_NAMES[level]} ...", flush=True)
        with ThreadPoolExecutor(max_workers=3) as pool:
            rows = list(
                pool.map(
                    lambda pair, lv=level: process(
                        pair[1], lv, pair[0], redactor, lv == "fax" and pair[0] < args.visual_docs
                    ),
                    enumerate(docs),
                )
            )
        all_rows[level] = rows
        summaries[level] = summarize(rows)
        if level == "fax":
            visual = summarize([r for r in rows if "visual_leaked" in r])
            for key in ("visual_removed", "visual_doc_leakage", "boxes_match_text"):
                summaries[level][key] = visual[key]
        s = summaries[level]
        print(f"  removed={s['removed']:.3f} doc_leakage={s['doc_leakage']:.3f} cer={s['cer']:.3f}", flush=True)
    (HERE / "charts").mkdir(exist_ok=True)
    chart(summaries, HERE / "charts" / "ocr_levels.png")
    args.out.write_text(write_report(summaries, all_rows, info), encoding="utf-8")
    (HERE / f"summary_ocr_{args.split}.json").write_text(
        json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "per_type"} for k, v in summaries.items()}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
