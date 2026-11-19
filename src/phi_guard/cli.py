"""Command-line interface: ``phi-guard scan|redact|inject|check|verify``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from . import __version__
from .audit import AuditLog
from .detectors import ALL_KINDS, scan
from .guard import Guard
from .injection import analyze
from .redactor import MODES, Redactor


def _read(path: str | None) -> str:
    if path is None or path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _kinds(value: str | None) -> list[str] | None:
    return [k.strip().upper() for k in value.split(",") if k.strip()] if value else None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="phi-guard", description="Redact patient data and screen for prompt injection.")
    p.add_argument("--version", action="version", version=f"phi-guard {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="list PHI found in a file (or stdin)")
    s.add_argument("file", nargs="?")
    s.add_argument("--kinds", help=f"comma-separated subset of: {','.join(ALL_KINDS)}")
    s.add_argument("--json", action="store_true", help="print JSON")

    r = sub.add_parser("redact", help="print a redacted copy")
    r.add_argument("file", nargs="?")
    r.add_argument("--mode", choices=MODES, default="pseudonymize")
    r.add_argument("--kinds")

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
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.cmd == "scan":
        findings = scan(_read(args.file), _kinds(args.kinds))
        if args.json:
            print(json.dumps([f.to_dict() for f in findings], indent=2))
        else:
            for f in findings:
                print(f"{f.start:>6}-{f.end:<6} {f.kind:<14} {f.text}")
            print(f"{len(findings)} finding(s)")
        return 0

    if args.cmd == "redact":
        print(Redactor(mode=args.mode).redact(_read(args.file), _kinds(args.kinds)).text, end="")
        return 0

    if args.cmd == "inject":
        report = analyze(_read(args.file))
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print(f"verdict: {report.verdict}  score: {report.score:.2f}")
            for f in report.findings:
                print(f"  - {f.rule} ({f.source}): {f.match[:60]!r}")
        return 2 if report.verdict == "block" else 0

    if args.cmd == "check":
        guard = Guard(Redactor(mode=args.mode), AuditLog(args.log))
        result = guard.inspect(_read(args.file), source=args.source, untrusted=True)
        if not result.allowed:
            assert result.injection is not None
            print(f"BLOCKED: prompt injection detected (score {result.injection.score:.2f})", file=sys.stderr)
            return 2
        print(result.text, end="")
        return 0

    if args.cmd == "verify":
        ok, line = AuditLog(args.log).verify()
        print("OK: log intact" if ok else f"TAMPERED: chain broken at line {line}")
        return 0 if ok else 1

    return 1  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
