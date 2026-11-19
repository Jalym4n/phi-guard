# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] - 2026-11-19

### Added
- Street address detection (`ADDRESS`), custom always/never word lists (`CUSTOM`), optional spaCy NER (`PERSON_NAME_NER`).
- Per-finding confidence and UTF-16 offset helpers for browser highlighting.
- Keep/Remove decisions and manual spans in `Redactor.redact()`; `restore_detailed()` reports unknown tokens.
- `documents.py`: text extraction from .txt / .docx / .pdf with content-type checks; redacted .docx output.
- `output_scan.py`: check AI responses for leaked identifiers and unknown tokens.
- `phi-guard batch`, `phi-guard output-scan`, `phi-guard eval` commands.
- Benchmark (`eval/`): 700 synthetic documents, 640 injection snippets, held-out templates, Presidio baseline, `eval/RESULTS.md`.
- phi-guard Studio: local web app (FastAPI + React) with remove, check, restore, batch, activity log, settings, help.
- Studio security controls: loopback bind, per-launch token, Host/Origin checks, strict CSP, in-memory uploads, idle vault clearing, keychain key storage, encrypted key export.
- Playwright E2E and axe accessibility tests; Windows/macOS/Linux PyInstaller builds and a Dockerfile.
- Docs: rewritten README with GIF and screenshots, STRIDE threat model, LEARNING.md study guide, DECISIONS.md.
- Detection improvements from dev-split analysis: name cues and propagation, negative context for order/lot numbers, lowercase postal codes, more street types, confusable and leetspeak normalization, `task_replacement` injection rule.

### Changed
- `Finding` gained `confidence` and `source`, and moved to `phi_guard.finding` (still re-exported from `detectors`).
- Name cues no longer cross line breaks.

## [0.1.0]

### Added
- Regex detectors for 10 PHI/PII types with Luhn validation and overlap resolution.
- HMAC-SHA256 pseudonymization and mask mode with an in-memory vault.
- Heuristic prompt-injection analysis (NFKC, zero-width, Base64, 8 rules).
- Hash-chained JSONL audit log; `Guard`; CLI (`scan`, `redact`, `inject`, `check`, `verify`).
