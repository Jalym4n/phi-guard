"""Command-line interface.

``phi-guard scan|redact|inject|check|verify|batch|output-scan|eval``
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .audit import AuditLog
from .detectors import ALL_KINDS, scan
from .dictionary import Dictionary, parse_terms
from .guard import Guard
from .injection import analyze
from .output_scan import scan_output
from .redactor import MODES, Redactor


def _read(path: str | None) -> str:
    if path is None or path == "-":
        return sys.stdin.read()
    if Path(path).suffix.lower() in (".docx", ".pdf"):
        from .documents import extract_text

        return extract_text(path).text
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _kinds(args: argparse.Namespace) -> list[str] | None:
    value: str | None = getattr(args, "kinds", None)
    kinds = [k.strip().upper() for k in value.split(",") if k.strip()] if value else list(ALL_KINDS)
    if getattr(args, "no_addresses", False):
        kinds = [k for k in kinds if k != "ADDRESS"]
    return kinds


def _dictionary(args: argparse.Namespace) -> Dictionary | None:
    always = parse_terms(Path(args.always).read_text(encoding="utf-8")) if getattr(args, "always", None) else []
    never = parse_terms(Path(args.never).read_text(encoding="utf-8")) if getattr(args, "never", None) else []
    return Dictionary(always, never) if (always or never) else None


def _detection_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--kinds", help=f"comma-separated subset of: {','.join(ALL_KINDS)}")
    p.add_argument("--no-addresses", action="store_true", help="turn off street address detection")
    p.add_argument("--always", metavar="FILE", help="word list: always remove these terms (one per line)")
    p.add_argument("--never", metavar="FILE", help="word list: never remove these terms (one per line)")
    p.add_argument("--ner", action="store_true", help="also find names with spaCy (needs the [ner] extra)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="phi-guard", description="Redact patient data and screen for prompt injection.")
    p.add_argument("--version", action="version", version=f"phi-guard {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="list PHI found in a file (or stdin)")
    s.add_argument("file", nargs="?")
    _detection_options(s)
    s.add_argument("--json", action="store_true", help="print JSON")

    r = sub.add_parser("redact", help="print a redacted copy")
    r.add_argument("file", nargs="?")
    r.add_argument("--mode", choices=MODES, default="pseudonymize")
    _detection_options(r)

    i = sub.add_parser("inject", help="score a document for prompt injection")
    i.add_argument("file", nargs="?")
    i.add_argument("--json", action="store_true")

    c = sub.add_parser("check", help="redact + injection screen + audit log")
    c.add_argument("file", nargs="?")
    c.add_argument("--log", default="phi-guard-audit.jsonl")
    c.add_argument("--source", default="cli")
    c.add_argument("--mode", choices=MODES, default="pseudonymize")

    v = sub.add_parser("verify", help="verify an audit log's hash chain")
    v.add_argument("log")

    b = sub.add_parser("batch", help="redact every .txt/.docx/.pdf in a folder")
    b.add_argument("folder")
    b.add_argument("--out", required=True, help="output folder (created if missing)")
    b.add_argument("--mode", choices=MODES, default="mask")
    b.add_argument("--no-recursive", action="store_true")
    b.add_argument("--log", help="also append one audit entry per file to this log")
    _detection_options(b)

    o = sub.add_parser("output-scan", help="check an AI response for leaked patient details")
    o.add_argument("file", nargs="?")
    o.add_argument("--json", action="store_true")

    e = sub.add_parser("eval", help="regenerate the benchmark dataset and results (run from the repo root)")
    e.add_argument("--quick", action="store_true", help="small dataset for a fast smoke run")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.cmd == "scan":
        findings = scan(_read(args.file), _kinds(args), dictionary=_dictionary(args), ner=args.ner)
        if args.json:
            print(json.dumps([f.to_dict() for f in findings], indent=2))
        else:
            for f in findings:
                print(f"{f.start:>6}-{f.end:<6} {f.kind:<16} {f.confidence:.2f}  {f.text}")
            print(f"{len(findings)} finding(s)")
        return 0

    if args.cmd == "redact":
        result = Redactor(mode=args.mode).redact(
            _read(args.file), _kinds(args), dictionary=_dictionary(args), ner=args.ner
        )
        print(result.text, end="")
        return 0

    if args.cmd == "inject":
        report = analyze(_read(args.file))
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print(f"verdict: {report.verdict}  score: {report.score:.2f}")
            for inj in report.findings:
                print(f"  - {inj.rule} ({inj.source}): {inj.match[:60]!r}")
        return 2 if report.verdict == "block" else 0

    if args.cmd == "check":
        guard = Guard(Redactor(mode=args.mode), AuditLog(args.log))
        checked = guard.inspect(_read(args.file), source=args.source, untrusted=True)
        if not checked.allowed:
            assert checked.injection is not None
            print(f"BLOCKED: prompt injection detected (score {checked.injection.score:.2f})", file=sys.stderr)
            return 2
        print(checked.text, end="")
        return 0

    if args.cmd == "verify":
        ok, line = AuditLog(args.log).verify()
        print("OK: log intact" if ok else f"TAMPERED: chain broken at line {line}")
        return 0 if ok else 1

    if args.cmd == "batch":
        return _batch(args)

    if args.cmd == "output-scan":
        findings = scan_output(_read(args.file))
        if args.json:
            print(json.dumps([f.to_dict() for f in findings], indent=2))
        else:
            for f in findings:
                print(f"{f.kind:<16} {f.text}")
            print("No patient details found." if not findings else f"{len(findings)} possible leak(s)")
        return 1 if findings else 0

    if args.cmd == "eval":
        return _eval(args)

    return 1  # pragma: no cover


def _batch(args: argparse.Namespace) -> int:
    from .batch import iter_folder, run_batch, summary_csv

    src, out = Path(args.folder), Path(args.out)
    if not src.is_dir():
        print(f"error: {src} is not a folder", file=sys.stderr)
        return 1
    if out.resolve().is_relative_to(src.resolve()):
        print("error: the output folder must not be inside the input folder", file=sys.stderr)
        return 1
    files = [(name, path.read_bytes()) for name, path in iter_folder(src, recursive=not args.no_recursive)]
    redactor = Redactor(mode=args.mode)
    log = AuditLog(args.log) if args.log else None
    items = run_batch(files, redactor, kinds=_kinds(args), dictionary=_dictionary(args), ner=args.ner)
    out.mkdir(parents=True, exist_ok=True)
    for it in items:
        if it.status == "done":
            target = out / it.output_name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(it.output)
        if log is not None:
            log.append("batch_file", source="cli", status=it.status, counts=it.counts, verdict=it.verdict or None)
        print(f"{it.status:<8} {it.name}" + (f"  ({it.reason})" if it.reason else ""))
    (out / "summary.csv").write_text(summary_csv(items), encoding="utf-8")
    done = sum(it.status == "done" for it in items)
    print(f"{done}/{len(items)} file(s) redacted -> {out}")
    return 0 if all(it.status != "error" for it in items) else 1


def _eval(args: argparse.Namespace) -> int:
    root = Path.cwd()
    if not (root / "eval" / "run.py").exists():
        print("error: run 'phi-guard eval' from the phi-guard repository root (eval/ not found)", file=sys.stderr)
        return 1
    gen = [sys.executable, "-m", "eval.generate"] + (["--quick"] if args.quick else [])
    run = [sys.executable, "-m", "eval.run"] + (["--quick"] if args.quick else [])
    for cmd in (gen, run):
        code = subprocess.call(cmd, cwd=root)
        if code:
            return code
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
