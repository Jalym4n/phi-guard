"""Run the benchmark and write eval/RESULTS.md plus charts.

Systems compared (PHI detection):

=====================================  ==================================================
System                                 Configuration
=====================================  ==================================================
phi-guard (regex only)                 v0.1 detectors, no address detection
phi-guard (default)                    all detectors incl. street addresses
phi-guard + clinic word list           default + the clinic's own phone/fax/address on
                                       the "never remove" list (what a clinic would set)
phi-guard + NER                        default + spaCy ``en_core_web_sm`` person names
Presidio                               ``presidio-analyzer`` out of the box,
                                       spaCy ``en_core_web_lg`` (its recommended model)
=====================================  ==================================================

Label mapping (system label -> benchmark label):

=====================  ======================  ================
Benchmark label        phi-guard kind          Presidio entity
=====================  ======================  ================
NAME                   PATIENT_NAME,           PERSON
                       PERSON_NAME_NER, CUSTOM
DATE_OF_BIRTH          DATE_OF_BIRTH           DATE_TIME
OHIP_NUMBER            OHIP_NUMBER             UK_NHS (10 digits; closest)
SIN                    SIN                     US_SSN (9 digits; closest)
CREDIT_CARD            CREDIT_CARD             CREDIT_CARD
EMAIL                  EMAIL                   EMAIL_ADDRESS
PHONE                  PHONE                   PHONE_NUMBER
POSTAL_CODE            POSTAL_CODE             (none)
ADDRESS                ADDRESS                 LOCATION
MRN                    MRN                     (none)
IP_ADDRESS             IP_ADDRESS              IP_ADDRESS
=====================  ======================  ================

Other Presidio entities (URL, NRP, US_DRIVER_LICENSE, ...) are not scored per
type, but they still count as redacted text when computing leakage.

Usage::

    python -m eval.run                 # test split (reported numbers)
    python -m eval.run --split dev     # development split
    python -m eval.run --quick         # skip Presidio and NER (fast smoke run)
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from phi_guard import __version__
from phi_guard.detectors import ALL_KINDS, scan
from phi_guard.dictionary import Dictionary, parse_terms
from phi_guard.injection import BLOCK_THRESHOLD, REVIEW_THRESHOLD, analyze

HERE = Path(__file__).parent
DATA = HERE / "data"
CHARTS = HERE / "charts"

LABELS = ["NAME", "DATE_OF_BIRTH", "OHIP_NUMBER", "SIN", "CREDIT_CARD", "EMAIL", "PHONE", "POSTAL_CODE", "ADDRESS",
          "MRN", "IP_ADDRESS"]  # fmt: skip

PHI_GUARD_MAP = {"PATIENT_NAME": "NAME", "PERSON_NAME_NER": "NAME", "CUSTOM": "NAME"}
PRESIDIO_MAP = {
    "PERSON": "NAME",
    "DATE_TIME": "DATE_OF_BIRTH",
    "UK_NHS": "OHIP_NUMBER",
    "US_SSN": "SIN",
    "CREDIT_CARD": "CREDIT_CARD",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "LOCATION": "ADDRESS",
    "IP_ADDRESS": "IP_ADDRESS",
}

DISPLAY = {"NAME": "Name", "DATE_OF_BIRTH": "Date of birth", "OHIP_NUMBER": "OHIP number", "SIN": "SIN",
           "CREDIT_CARD": "Credit card", "EMAIL": "Email", "PHONE": "Phone", "POSTAL_CODE": "Postal code",
           "ADDRESS": "Street address", "MRN": "MRN", "IP_ADDRESS": "IP address"}  # fmt: skip

Pred = tuple[int, int, str | None]  # start, end, benchmark label (None = unmapped)

# Reference palette, light mode (see the dataviz notes in DECISIONS.md).
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# --- systems -----------------------------------------------------------------


def phi_guard_system(
    kinds: list[str], dictionary: Dictionary | None = None, ner: bool = False
) -> Callable[[str], list[Pred]]:
    def run(text: str) -> list[Pred]:
        out: list[Pred] = []
        for f in scan(text, kinds, dictionary=dictionary, ner=ner):
            out.append((f.start, f.end, PHI_GUARD_MAP.get(f.kind, f.kind if f.kind in LABELS else None)))
        return out

    return run


def presidio_system() -> Callable[[str], list[Pred]] | None:
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider
    except ImportError:
        return None
    import spacy.util

    model = "en_core_web_lg" if spacy.util.is_package("en_core_web_lg") else "en_core_web_sm"
    provider = NlpEngineProvider(
        nlp_configuration={"nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": model}]}
    )
    engine = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])
    presidio_system.model = model  # type: ignore[attr-defined]

    def run(text: str) -> list[Pred]:
        results = engine.analyze(text=text, language="en")
        # Presidio can return overlapping results; keep the highest score, then the longest
        # (the same rule its anonymizer applies) so duplicates are not double-counted.
        ordered = sorted(results, key=lambda r: (-r.score, -(r.end - r.start)))
        kept: list[Any] = []
        for r in ordered:
            if not any(r.start < k.end and k.start < r.end for k in kept):
                kept.append(r)
        return [(r.start, r.end, PRESIDIO_MAP.get(r.entity_type)) for r in kept]

    return run


# --- metrics -----------------------------------------------------------------


@dataclass
class Counts:
    tp_pred: int = 0  # predictions that match a gold span (precision numerator)
    n_pred: int = 0
    tp_gold: int = 0  # gold spans matched by a prediction (recall numerator)
    n_gold: int = 0

    def p(self) -> float:
        return self.tp_pred / self.n_pred if self.n_pred else 0.0

    def r(self) -> float:
        return self.tp_gold / self.n_gold if self.n_gold else 0.0

    def f1(self) -> float:
        p, r = self.p(), self.r()
        return 2 * p * r / (p + r) if p + r else 0.0


@dataclass
class SystemResult:
    name: str
    exact: dict[str, Counts] = field(default_factory=lambda: defaultdict(Counts))
    overlap: dict[str, Counts] = field(default_factory=lambda: defaultdict(Counts))
    leaked_docs: int = 0
    n_docs: int = 0
    leaked_spans: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    seconds: float = 0.0
    false_negatives: list[tuple[str, str]] = field(default_factory=list)  # (label, context)
    false_positives: list[tuple[str, str]] = field(default_factory=list)

    def total(self, which: str) -> Counts:
        table = self.exact if which == "exact" else self.overlap
        c = Counts()
        for k in LABELS:
            v = table[k]
            c.tp_pred += v.tp_pred
            c.n_pred += v.n_pred
            c.tp_gold += v.tp_gold
            c.n_gold += v.n_gold
        return c

    def leakage(self) -> float:
        return self.leaked_docs / self.n_docs if self.n_docs else 0.0


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _context(text: str, s: int, e: int, width: int = 35) -> str:
    left = text[max(0, s - width) : s].replace("\n", " ⏎ ")
    right = text[e : e + width].replace("\n", " ⏎ ")
    return f"…{left}**{text[s:e]}**{right}…"


def score_system(name: str, system: Callable[[str], list[Pred]], docs: list[dict[str, Any]]) -> SystemResult:
    res = SystemResult(name)
    t0 = time.perf_counter()
    all_preds = [system(d["text"]) for d in docs]
    res.seconds = time.perf_counter() - t0
    for doc, preds in zip(docs, all_preds, strict=True):
        text = doc["text"]
        gold = [s for s in doc["spans"] if not s.get("ignore")]
        ignore = [(s["start"], s["end"]) for s in doc["spans"] if s.get("ignore")]
        res.n_docs += 1

        # Predictions that only touch an ignored span (clinician names) are not scored.
        scored = [
            p
            for p in preds
            if p[2] is not None
            and not (
                any(_overlaps(p[:2], i) for i in ignore)
                and not any(_overlaps(p[:2], (g["start"], g["end"])) for g in gold)
            )
        ]
        for label in LABELS:
            g_spans = [(g["start"], g["end"]) for g in gold if g["kind"] == label]
            p_spans = [(p[0], p[1]) for p in scored if p[2] == label]
            for table, match in ((res.exact, lambda a, b: a == b), (res.overlap, _overlaps)):
                c = table[label]
                c.n_gold += len(g_spans)
                c.n_pred += len(p_spans)
                c.tp_gold += sum(any(match(p, g) for p in p_spans) for g in g_spans)
                c.tp_pred += sum(any(match(p, g) for g in g_spans) for p in p_spans)
            for p in p_spans:
                if not any(_overlaps(p, g) for g in g_spans) and len(res.false_positives) < 400:
                    res.false_positives.append((label, _context(text, *p)))

        # Leakage: any character of any gold identifier not covered by any prediction.
        covered = [False] * len(text)
        for s, e, _ in preds:
            for i in range(s, e):
                covered[i] = True
        leaked = False
        for g in gold:
            if not all(covered[g["start"] : g["end"]]):
                leaked = True
                res.leaked_spans[g["kind"]] += 1
                if len(res.false_negatives) < 400:
                    res.false_negatives.append((g["kind"], _context(text, g["start"], g["end"])))
        res.leaked_docs += leaked
    return res


# --- injection ---------------------------------------------------------------


def injection_eval(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [(r, analyze(r["text"]).score) for r in rows]
    mal = [s for r, s in scored if r["label"] == 1]
    ben = [s for r, s in scored if r["label"] == 0]
    thresholds = [round(i * 0.05, 2) for i in range(1, 20)]
    curve = [(t, sum(s >= t for s in mal) / len(mal), sum(s >= t for s in ben) / len(ben)) for t in thresholds]
    by_obf: dict[str, list[float]] = defaultdict(list)
    for r, s in scored:
        if r["label"] == 1:
            by_obf[r["obfuscation"]].append(s)
    ben_by_family: dict[str, list[float]] = defaultdict(list)
    for r, s in scored:
        if r["label"] == 0:
            ben_by_family[r["family"]].append(s)
    misses = [r["text"] for r, s in scored if r["label"] == 1 and s < REVIEW_THRESHOLD][:8]
    fps = [r["text"] for r, s in scored if r["label"] == 0 and s >= REVIEW_THRESHOLD][:6]
    return {"n_mal": len(mal), "n_ben": len(ben), "curve": curve, "by_obf": dict(by_obf), "mal": mal, "ben": ben,
            "misses": misses, "fps": fps, "ben_by_family": dict(ben_by_family)}  # fmt: skip


def rate(scores: list[float], t: float) -> float:
    return sum(s >= t for s in scores) / len(scores) if scores else 0.0


# --- charts ------------------------------------------------------------------


def _style(ax: Any) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def make_charts(results: list[SystemResult], inj: dict[str, Any]) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    CHARTS.mkdir(exist_ok=True)
    plt.rcParams.update({"font.size": 10, "text.color": INK, "axes.labelcolor": INK_2, "figure.facecolor": SURFACE})
    files = []

    # 1. Per-type F1 (overlap match) for three headline systems.
    picks = [r for r in results if r.name in ("phi-guard (default)", "phi-guard + NER", "Presidio")]
    fig, ax = plt.subplots(figsize=(8, 6.2), dpi=150)
    _style(ax)
    n, h = len(picks), 0.8 / max(1, len(picks))
    labels = list(reversed(LABELS))
    for i, r in enumerate(picks):
        ys = [j + (n - 1 - i) * h - 0.4 + h / 2 for j in range(len(labels))]
        vals = [r.overlap[k].f1() for k in labels]
        ax.barh(ys, vals, height=h - 0.03, color=SERIES[i], label=r.name)
        for y, v in zip(ys, vals, strict=True):
            if v == 0:  # a zero-length bar is invisible; say so explicitly
                ax.text(0.005, y, "0", va="center", fontsize=7, color=INK_2)
    ax.set_yticks(range(len(labels)), [DISPLAY[k] for k in labels], color=INK)
    ax.set_xlim(0, 1)
    ax.set_xlabel("F1 score (overlap match), test split")
    ax.set_title("Detection quality by type", loc="left", fontsize=12, color=INK, pad=28)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(CHARTS / "f1_by_type.png")
    plt.close(fig)
    files.append("charts/f1_by_type.png")

    # 2. Document leakage rate per system (single series, direct labels).
    fig, ax = plt.subplots(figsize=(8, 3.4), dpi=150)
    _style(ax)
    names = [r.name for r in results][::-1]
    vals = [r.leakage() * 100 for r in results][::-1]
    ax.barh(names, vals, height=0.6, color=SERIES[0])
    for y, v in enumerate(vals):
        ax.text(v + 1, y, f"{v:.1f}%", va="center", fontsize=9, color=INK)
    ax.set_xlim(0, 110)
    ax.set_xlabel("% of documents where at least one identifier survived (lower is better)")
    ax.set_title("Leakage rate", loc="left", fontsize=12, color=INK, pad=12)
    ax.tick_params(axis="y", colors=INK)
    fig.tight_layout()
    fig.savefig(CHARTS / "leakage.png")
    plt.close(fig)
    files.append("charts/leakage.png")

    # 3. Injection threshold curve.
    fig, ax = plt.subplots(figsize=(8, 4), dpi=150)
    _style(ax)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ts = [c[0] for c in inj["curve"]]
    ax.plot(ts, [c[1] * 100 for c in inj["curve"]], color=SERIES[0], linewidth=2, marker="o", markersize=4,
            label="Detection rate (malicious flagged)")  # fmt: skip
    ax.plot(ts, [c[2] * 100 for c in inj["curve"]], color=SERIES[1], linewidth=2, marker="s", markersize=4,
            label="False positive rate (benign flagged)")  # fmt: skip
    for t, name in ((REVIEW_THRESHOLD, "review"), (BLOCK_THRESHOLD, "block")):
        ax.axvline(t, color=INK_2, linewidth=1, linestyle=(0, (3, 3)))
        ax.text(t + 0.01, 96, name, fontsize=9, color=INK_2)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 100)
    ax.set_xlabel("Score threshold")
    ax.set_ylabel("% of snippets")
    ax.set_title("Prompt-injection screening: threshold trade-off", loc="left", fontsize=12, color=INK, pad=12)
    ax.legend(loc="center right", frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(CHARTS / "injection_threshold.png")
    plt.close(fig)
    files.append("charts/injection_threshold.png")
    return files


# --- report ------------------------------------------------------------------


def pct(x: float) -> str:
    return f"{x * 100:.1f}"


def write_results(
    results: list[SystemResult],
    inj: dict[str, Any],
    charts: list[str],
    split: str,
    n_docs: int,
    n_gold: int,
    subsets: dict[str, list[SystemResult]] | None = None,
) -> str:
    L: list[str] = []
    model = getattr(presidio_system, "model", "n/a")
    L += [
        "# Benchmark results",
        "",
        "> Auto-generated by `python -m eval.run` (or `phi-guard eval`). Do not edit by hand;",
        "> the discussion section is kept in `eval/discussion.md` and inserted below.",
        "",
        f"* phi-guard version: **{__version__}**",
        f"* Split: **{split}** ({n_docs} synthetic documents, {n_gold} labelled identifiers). "
        "Rules were developed on the separate `dev` split only.",
        f"* Presidio: `presidio-analyzer` default recognizers, spaCy `{model}`.",
        "* All data is synthetic, generated by `eval/generate.py` with fixed seeds.",
        "* Scanned and faxed documents (OCR): see [RESULTS_OCR.md](RESULTS_OCR.md).",
        "",
        "## Headline",
        "",
        "Overall = micro-average over all identifier types. *Exact* requires identical span boundaries and type; "
        "*overlap* requires the same type and any character overlap. **Leakage** is the share of documents in which "
        "at least one character of at least one identifier was left unredacted (any system label counts as redacted).",
        "",
        "| System | Precision (exact) | Recall (exact) | F1 (exact) | Precision (overlap) | Recall (overlap) "
        "| F1 (overlap) | Leakage rate | Time (s) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        e, o = r.total("exact"), r.total("overlap")
        L.append(
            f"| {r.name} | {pct(e.p())} | {pct(e.r())} | {pct(e.f1())} | {pct(o.p())} | {pct(o.r())} | "
            f"{pct(o.f1())} | **{pct(r.leakage())}%** | {r.seconds:.1f} |"
        )
    if subsets:
        L += [
            "",
            "## Generalization: seen vs held-out templates",
            "",
            "The test split mixes documents built from the four development templates (*seen*) with a nursing-handover "
            "template that exists only in the test split (*held-out*), written with cues and formats the rules were "
            "never developed against. The gap between the two columns is the honest estimate of how much the seen-template "
            "numbers flatter the rules.",
            "",
            "| System | Recall, seen | Recall, held-out | Precision, seen | Precision, held-out | Leakage, seen | Leakage, held-out |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        seen, held = subsets["seen"], subsets["held_out"]
        for a, b in zip(seen, held, strict=True):
            ta, tb = a.total("overlap"), b.total("overlap")
            L.append(
                f"| {a.name} | {pct(ta.r())} | {pct(tb.r())} | {pct(ta.p())} | {pct(tb.p())} | "
                f"{pct(a.leakage())}% | **{pct(b.leakage())}%** |"
            )
    L += ["", f"![Leakage rate]({charts[1]})", "", "## Per-type results (overlap match)", ""]
    header = "| Type | Gold | " + " | ".join(f"{r.name} P / R / F1" for r in results) + " |"
    L += [header, "|---|---:|" + "---:|" * len(results)]
    for k in LABELS:
        cells = [f"{pct(r.overlap[k].p())} / {pct(r.overlap[k].r())} / {pct(r.overlap[k].f1())}" for r in results]
        L.append(f"| {k} | {results[0].overlap[k].n_gold} | " + " | ".join(cells) + " |")
    L += ["", f"![F1 by type]({charts[0]})", "", "## Per-type results (exact match)", ""]
    L += [header, "|---|---:|" + "---:|" * len(results)]
    for k in LABELS:
        cells = [f"{pct(r.exact[k].p())} / {pct(r.exact[k].r())} / {pct(r.exact[k].f1())}" for r in results]
        L.append(f"| {k} | {results[0].exact[k].n_gold} | " + " | ".join(cells) + " |")
    L += [
        "",
        "## Identifiers left unredacted, by type",
        "",
        "| Type | Gold | " + " | ".join(r.name for r in results) + " |",
    ]
    L += ["|---|---:|" + "---:|" * len(results)]
    for k in LABELS:
        L.append(
            f"| {k} | {results[0].overlap[k].n_gold} | "
            + " | ".join(f"{r.leaked_spans.get(k, 0)}" for r in results)
            + " |"
        )

    # Injection
    L += [
        "",
        "## Prompt-injection screening",
        "",
        f"{inj['n_mal']} malicious and {inj['n_ben']} benign snippets (test split). A snippet is *flagged* when its "
        "score reaches the threshold. Studio shows amber (review) at "
        f"{REVIEW_THRESHOLD} and red (block) at {BLOCK_THRESHOLD}.",
        "",
        "| Threshold | Detection rate | False positive rate |",
        "|---|---:|---:|",
        f"| review ({REVIEW_THRESHOLD}) | {pct(rate(inj['mal'], REVIEW_THRESHOLD))}% | "
        f"{pct(rate(inj['ben'], REVIEW_THRESHOLD))}% |",
        f"| block ({BLOCK_THRESHOLD}) | {pct(rate(inj['mal'], BLOCK_THRESHOLD))}% | "
        f"{pct(rate(inj['ben'], BLOCK_THRESHOLD))}% |",
        "",
        "Detection rate at the review threshold, by obfuscation:",
        "",
        "| Obfuscation | Snippets | Detected (review) | Detected (block) |",
        "|---|---:|---:|---:|",
    ]
    for obf, scores in sorted(inj["by_obf"].items()):
        L.append(
            f"| {obf} | {len(scores)} | {pct(rate(scores, REVIEW_THRESHOLD))}% | {pct(rate(scores, BLOCK_THRESHOLD))}% |"
        )
    L += [
        "",
        "False positive rate on benign snippets, by kind (`held_out` = phrasings never seen during development):",
        "",
    ]
    L += ["| Benign kind | Snippets | Flagged (review) | Flagged (block) |", "|---|---:|---:|---:|"]
    for fam, scores in sorted(inj["ben_by_family"].items()):
        L.append(
            f"| {fam} | {len(scores)} | {pct(rate(scores, REVIEW_THRESHOLD))}% | {pct(rate(scores, BLOCK_THRESHOLD))}% |"
        )
    L += ["", "| Threshold | Detection rate | False positive rate |", "|---:|---:|---:|"]
    for t, tpr, fpr in inj["curve"]:
        L.append(f"| {t:.2f} | {pct(tpr)}% | {pct(fpr)}% |")
    L += ["", f"![Injection threshold curve]({charts[2]})", ""]

    # Failure examples
    default = next(r for r in results if r.name == "phi-guard (default)")
    L += ["## Failure examples (phi-guard default, synthetic)", "", "**Missed identifiers (false negatives):**", ""]
    seen: dict[str, int] = defaultdict(int)
    for label, ctx in default.false_negatives:
        if seen[label] < 2:
            seen[label] += 1
            L.append(f"* `{label}`: {ctx}")
    L += ["", "**False alarms (false positives):**", ""]
    seen = defaultdict(int)
    for label, ctx in default.false_positives:
        if seen[label] < 2:
            seen[label] += 1
            L.append(f"* `{label}`: {ctx}")
    L += ["", "**Injection attacks scored below the review threshold:**", ""]
    L += [f"* `{t[:140]}`" for t in inj["misses"]]
    L += ["", "**Benign snippets flagged for review:**", ""]
    L += [f"* `{t[:140]}`" for t in inj["fps"]]
    L.append("")
    disc = HERE / "discussion.md"
    if disc.exists():
        L += [disc.read_text(encoding="utf-8").strip(), ""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=["dev", "test"], default="test")
    ap.add_argument("--quick", action="store_true", help="skip Presidio and NER")
    ap.add_argument("--out", type=Path, default=HERE / "RESULTS.md")
    args = ap.parse_args(argv)

    docs = load_jsonl(DATA / f"phi_{args.split}.jsonl")
    terms = parse_terms((DATA / f"clinic_never_remove_{args.split}.txt").read_text(encoding="utf-8"))
    no_addr = [k for k in ALL_KINDS if k != "ADDRESS"]
    systems: list[tuple[str, Callable[[str], list[Pred]]]] = [
        ("phi-guard (regex only)", phi_guard_system(no_addr)),
        ("phi-guard (default)", phi_guard_system(list(ALL_KINDS))),
        ("phi-guard + clinic word list", phi_guard_system(list(ALL_KINDS), Dictionary(never=terms))),
    ]
    if not args.quick:
        from phi_guard import ner

        if ner.is_available():
            systems.append(("phi-guard + NER", phi_guard_system(list(ALL_KINDS), ner=True)))
        else:
            print("note: spaCy en_core_web_sm not installed; skipping phi-guard + NER")
        presidio = presidio_system()
        if presidio is not None:
            systems.append(("Presidio", presidio))
        else:
            print("note: presidio-analyzer not installed; skipping the Presidio baseline")

    results = []
    for name, system in systems:
        print(f"running {name} ...", flush=True)
        results.append(score_system(name, system, docs))
    subsets: dict[str, list[SystemResult]] = {}
    held = [d for d in docs if d.get("held_out")]
    if held:
        seen = [d for d in docs if not d.get("held_out")]
        subsets = {
            "seen": [score_system(name, system, seen) for name, system in systems],
            "held_out": [score_system(name, system, held) for name, system in systems],
        }
    inj = injection_eval(load_jsonl(DATA / f"injection_{args.split}.jsonl"))
    charts = make_charts(results, inj)
    n_gold = sum(1 for d in docs for s in d["spans"] if not s.get("ignore"))
    args.out.write_text(
        write_results(results, inj, charts, args.split, len(docs), n_gold, subsets or None), encoding="utf-8"
    )
    summary = {
        r.name: {
            "precision": r.total("overlap").p(),
            "recall": r.total("overlap").r(),
            "f1": r.total("overlap").f1(),
            "leakage": r.leakage(),
        }
        for r in results
    }
    (HERE / f"summary_{args.split}.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    for r in results:
        o = r.total("overlap")
        print(f"{r.name:<30} P={o.p():.3f} R={o.r():.3f} F1={o.f1():.3f} leakage={r.leakage():.3f}")
    print(
        f"injection: detect@review={rate(inj['mal'], REVIEW_THRESHOLD):.3f} fpr@review={rate(inj['ben'], REVIEW_THRESHOLD):.3f}"
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
