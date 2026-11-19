# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] - unreleased

### Added
- Street address detection (`ADDRESS`), custom always/never word lists (`CUSTOM`), optional spaCy NER (`PERSON_NAME_NER`).
- Per-finding confidence and UTF-16 offset helpers for browser highlighting.
- Keep/Remove decisions and manual spans in `Redactor.redact()`; `restore_detailed()` reports unknown tokens.
- `documents.py`: text extraction from .txt / .docx / .pdf with content-type checks; redacted .docx output.
- `output_scan.py`: check AI responses for leaked identifiers and unknown tokens.
- `phi-guard batch`, `phi-guard output-scan`, `phi-guard eval` commands.
- Benchmark (`eval/`): 700 synthetic documents, 640 injection snippets, held-out templates, Presidio baseline, `eval/RESULTS.md`.
- Detection improvements from dev-split analysis: name cues and propagation, negative context for order/lot numbers, lowercase postal codes, more street types, confusable and leetspeak normalization, `task_replacement` injection rule.

## [0.1.0]

### Added
- Regex detectors for 10 PHI/PII types with Luhn validation and overlap resolution.
- HMAC-SHA256 pseudonymization and mask mode with an in-memory vault.
- Heuristic prompt-injection analysis (NFKC, zero-width, Base64, 8 rules).
- Hash-chained JSONL audit log; `Guard`; CLI (`scan`, `redact`, `inject`, `check`, `verify`).
