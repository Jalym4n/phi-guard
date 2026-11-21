# phi-guard

**Remove patient details and catch prompt injection before clinical text reaches an AI tool, with a point-and-click app clinicians can use without training.**

[![Python CI](https://github.com/jalym4n/phi-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/jalym4n/phi-guard/actions/workflows/ci.yml)
[![Studio UI and E2E](https://github.com/jalym4n/phi-guard/actions/workflows/ui.yml/badge.svg)](https://github.com/jalym4n/phi-guard/actions/workflows/ui.yml)
![coverage](https://img.shields.io/badge/coverage-97%25%20(%E2%89%A590%25%20enforced)-brightgreen)
![python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)
![license](https://img.shields.io/badge/license-MIT-lightgrey)

![phi-guard Studio: paste a note, find patient details, keep one, copy the safe version](docs/studio-demo.gif)

phi-guard has two parts:

* **phi-guard**, a dependency-free Python library and CLI that finds Canadian patient identifiers (OHIP, SIN, MRN, names, dates of birth, addresses and more), replaces them with reversible HMAC codes or permanent labels, screens documents for prompt injection, and keeps a tamper-evident activity log. It reads typed documents and **scanned PDFs and faxes** (offline OCR), and can produce a **redacted copy of the scan** with black boxes over the details.
* **phi-guard Studio**, a local web app built on the library for nurses, clinic managers and physicians. It runs only on the user's own computer and never connects to the internet.

All data in this repository, its tests, screenshots and benchmark is **synthetic**.

---

## For healthcare workers

### Install

| Your computer | What to do |
|---|---|
| **Windows** | Download `phi-guard-studio-…-windows.zip` from [Releases](https://github.com/jalym4n/phi-guard/releases), unzip it, open the folder and double-click **phi-guard-studio.exe**. If Windows shows "Windows protected your PC", click **More info → Run anyway** (the app is not code-signed). |
| **Mac** | Download `phi-guard-studio-…-macos.zip`, unzip it, open the folder, then **right-click → Open** on **phi-guard-studio** the first time (the app is not notarized). |
| **Reading scans and faxes** | The Windows download includes the text-recognition add-on (Tesseract). On a Mac, install it once with `brew install tesseract tesseract-lang`. Typed documents work without it; Studio's Settings page says whether it's ready. |
| **IT-managed / Docker** | `docker build -t phi-guard-studio .` then `docker run --rm -p 127.0.0.1:8765:8765 phi-guard-studio`, and open the address printed in the logs (it includes the session token). Each tagged release also attaches the image as `phi-guard-studio-docker.tar.gz` (`docker load < …`). |

Studio opens in your web browser. A small window stays open while it runs; closing it stops Studio and clears everything it remembered.

### Use it

| Screen | What it is for |
|---|---|
| ![Remove patient details](docs/screenshots/1-remove-light.png) | **Remove patient details.** Paste a note (or add a .txt, .docx, .pdf, or a scanned fax or photo), click **Find patient details**, check the highlights, click **Copy safe text**. Three clicks. Click **Keep** on anything that should stay, or select missed text and choose **Also remove this**. For scans, Studio shows how confident it was and the scanned pages to compare against, and can download the scan itself with black boxes over the details. |
| ![Check a document](docs/screenshots/3-check-light.png) | **Check a document.** Before adding a policy or letter to an AI tool or knowledge base, check it for hidden instructions. Green: looks safe. Amber: needs a person to review. Red: do not use. |
| ![Restore names](docs/screenshots/4-restore-dark.png) | **Restore names.** Paste an AI answer with codes like `[PATIENT_NAME_a2b6c3d4]` to put the real details back, for your own records, while Studio is open. Also checks AI answers for details that should not be there. |
| ![Activity log](docs/screenshots/5-activity-light.png) | **Activity log.** What was done and how many details were handled, never the details themselves. One click proves the log hasn't been altered. |

More screens, in light and dark mode: [`docs/screenshots/`](docs/screenshots/). Batch mode (a folder of files in, a ZIP out with a summary sheet) is a tab on the first screen.

**Is anything sent anywhere?** No. Studio talks only to itself at `127.0.0.1`. You can check: turn off Wi-Fi and it works the same.

---

## For developers

### Install from source

```bash
pip install -e ".[studio]"
```

```bash
phi-guard-studio
```

The core library alone has no dependencies: `pip install -e .`. Optional extras: `[studio]` (web app, .docx/.pdf, scans), `[ocr]` (scans without the web app), `[ner]` (spaCy names), `[eval]` (benchmark), `[dev]`. Reading scans also needs the [Tesseract](https://tesseract-ocr.github.io/) program (`apt install tesseract-ocr tesseract-ocr-fra`, `brew install tesseract tesseract-lang`, or the Windows installer); check with `phi-guard ocr-status`.

### Library

```python
from phi_guard import Redactor, Dictionary, analyze, scan_output

redactor = Redactor(key="from-your-secret-store")
result = redactor.redact(
    "Patient: Eleanor Whitfield, OHIP 5271-938-465, seen at Lakeview Clinic.",
    dictionary=Dictionary(always=["Lakeview Clinic"]),
)
result.text  # 'Patient: [PATIENT_NAME_…], OHIP [OHIP_NUMBER_…], seen at [CUSTOM_…].'
redactor.restore(result.text)  # original text, from the in-memory vault
analyze(open("examples/poisoned_doc.txt").read()).verdict  # 'block'
scan_output("Call her at 416-555-0142", redactor.known_tokens)  # flags the leaked phone number
```

`Redactor.redact()` also takes `keep=[(start, end), …]` (findings the user chose to keep) and `manual=[…]` (extra spans); anything not explicitly kept is removed.

### CLI

```bash
phi-guard redact examples/sample_note.txt --mode mask
```

```bash
phi-guard inject examples/poisoned_doc.txt
```

```bash
phi-guard batch referrals/ --out redacted/ --always staff_names.txt
```

```bash
phi-guard verify phi-guard-audit.jsonl
```

Also `scan`, `check` (redact + screen + log), `output-scan`, `ocr-status`, and `eval`. `scan`, `redact` and `batch` read scanned PDFs and fax images (`.tif`, `.png`, `.jpg`); `batch` also writes a `*.redacted-scan.pdf` for each scan.

### Studio API

All endpoints are under `/api` on `127.0.0.1`, require the per-launch `X-PHI-Guard-Token` header, and use UTF-16 offsets so browser highlights line up: `scan`, `redact`, `redact/docx`, `extract`, `inject`, `restore`, `output-scan`, `batch`, `audit`, `audit/verify`, `settings`, `key/rotate|export|import`, `session`, `health`. See [`src/phi_guard_studio/api/`](src/phi_guard_studio/api/).

---

## Results

Benchmark on 500 synthetic clinical documents (3,815 labelled identifiers), test split only; rules were developed on a separate dev split and frozen in a commit before the first test run. Full tables, charts and failure analysis: **[eval/RESULTS.md](eval/RESULTS.md)**. Reproduce with `make eval`.

| System | Precision | Recall | F1 | Leakage rate* |
|---|---:|---:|---:|---:|
| phi-guard, regex only (v0.1 detectors) | 72.0 | 74.6 | 73.3 | 71.4% |
| phi-guard, default (v0.2) | 69.1 | 82.4 | 75.2 | 22.0% |
| phi-guard + clinic word list | **99.8** | 82.4 | **90.3** | 22.0% |
| phi-guard + spaCy NER | 64.7 | **93.4** | 76.5 | 22.0% |
| Microsoft Presidio (default, `en_core_web_lg`) | 35.8 | 58.7 | 44.5 | 92.2% |

\*Share of documents in which at least one identifier survived. Overlap match, micro-averaged.

**Scans and faxes** ([eval/RESULTS_OCR.md](eval/RESULTS_OCR.md)): the same test documents rendered as page images and read with Studio's OCR.

| Input | Identifiers removed | Documents with any leak |
|---|---:|---:|
| Typed text | 82.4% | 24.0% |
| Clean office scan | 81.6% | 28.7% |
| Standard fax | 79.5% | 41.3% |
| Bad fax | 67.2% | 77.3% |

Clean scans cost almost nothing; faxes add leaks, mostly because one misread digit breaks a health card number's checksum or a misread "MRN:" loses its cue. On the redacted copy of the scan, the black boxes cover 99.3% of the details removed from the text.

**The honest part.** 20% of the test documents use a template written *only* for the test split. On familiar templates phi-guard's recall is 99.5% and 2.5% of documents leak; on the unseen template recall falls to 37% and **every** document leaks, for phi-guard and Presidio alike (an unsupported date format and uncued names). Rule-based de-identification is only as good as the formats it was written for, which is why Studio puts a human review step before every copy. Prompt-injection screening flags 70% of attacks for review with a 1.9% false-alarm rate, and misses phrasings it has never seen.

---

## Architecture

```mermaid
flowchart LR
    subgraph Computer["User's computer"]
        B["Browser<br/>React UI"] -- "fetch /api + X-PHI-Guard-Token<br/>127.0.0.1 only" --> S["Studio server<br/>FastAPI + security middleware"]
        S --> L["phi_guard library<br/>detectors · redactor · injection · audit"]
        S --> V[("Vault<br/>in memory only")]
        S --> K[("OS keychain<br/>HMAC key")]
        S --> A[("Activity log<br/>hash-chained JSONL<br/>counts only")]
        S --> C[("Settings JSON")]
    end
    U(("Clinician")) --> B
    B -. "safe text (copied by the user)" .-> AI["AI tool"]
```

| Path | What lives there |
|---|---|
| `src/phi_guard/` | Dependency-free core: `detectors`, `addresses`, `dictionary`, `ner` (optional), `redactor`, `injection`, `output_scan`, `documents`, `batch`, `audit`, `guard`, `cli` |
| `src/phi_guard_studio/` | FastAPI app, security middleware, keystore, settings, launcher, built UI in `static/` |
| `studio-ui/` | React + TypeScript + Vite + Tailwind source, Vitest and Playwright tests |
| `eval/` | Dataset generator, benchmark runner, `RESULTS.md`, charts |
| `packaging/` | PyInstaller spec and build script; `Dockerfile` at the root |
| `docs/` | `THREAT_MODEL.md`, `LEARNING.md`, screenshots |

## Security design

Studio is a web server on the user's own machine, so it is built to resist the websites the user visits as well as plain mistakes:

* **Loopback only.** Binds to `127.0.0.1` on a random port; refuses `0.0.0.0` without `--allow-network`.
* **Per-launch session token** in a custom header (blocks cross-site requests), **Host header check** (blocks DNS rebinding) and **Origin check**.
* **Strict Content Security Policy** (`default-src 'self'`, no inline script, no external origins), plus `nosniff`, `no-referrer`, `DENY` framing, same-origin opener policy and `no-store` on API responses.
* **No network calls.** Tests block every non-loopback connection while driving full workflows over a real socket.
* **No patient data on disk** unless the user downloads it: uploads stay in memory (a test fails if a temp file appears), OCR runs Tesseract through pipes rather than temp files, the activity log stores counts only, and file names are never logged.
* **Redacted scans hide what they cover:** image-only PDFs with no text layer, one box per detail per line so word lengths aren't revealed.
* **Uploads checked by content**, not extension; executables and archives are refused; batch paths are sanitized against zip slip; images are capped in size and pages (decompression bombs), and OCR runs in a separate, time-limited process.
* **Vault in memory only**, cleared on Start over, exit, key change and after 30 idle minutes (with a visible countdown).
* **Key** in the OS keychain (fallback: an encrypted file, clearly labelled); export uses scrypt + AES-256-GCM.
* `pip-audit`, `npm audit` and Dependabot in CI.

Each control has an automated test. Full STRIDE analysis: [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

## Quality

* 179 Python tests (97% line coverage, 90% enforced), mypy strict, ruff.
* 16 Vitest component tests; 22 Playwright end-to-end tests against the real server, including a faxed referral.
* axe-core: zero serious or critical WCAG 2.1 AA violations on every screen, light and dark.
* CI: Python 3.10 to 3.13, UI and E2E, Docker smoke test, release builds on tags.

## Limitations

* Detection is rule-based plus optional NER. It misses formats it wasn't written for (see Results), French-language notes, and handwriting. Always review before sharing.
* OCR can misread names and numbers, especially on poor faxes (see the scan results). Studio shows confidence and the scanned pages so staff can check; the redacted scan only covers what was detected.
* Prompt-injection screening is heuristic. It catches known patterns and common obfuscations, not novel phrasing.
* The hash-chained log proves internal consistency; someone who can rewrite the whole file can rebuild the chain. Anchor the latest hash elsewhere for stronger guarantees.
* Without an OS keychain, the key-file fallback only deters casual copying.
* Redacted PDFs are produced as text, and redacted .docx files simplify formatting inside changed paragraphs.
* The benchmark is synthetic; it cannot stand in for evaluation on real clinical notes.
* Desktop builds are not code-signed.

## Roadmap

* A date parser behind DOB cues, case-insensitive address matching, French street forms.
* Scan-aware detection: tolerate one misread digit or label character in OCR text, and highlight low-confidence words in review.
* NER on by default in Studio, with a drug-name and eponym allowlist.
* Evaluation on the n2c2 2014 de-identification corpus (under its data use agreement).
* A small learned prompt-injection classifier as a second stage.
* Signed and notarized desktop builds.

## Documentation

[eval/RESULTS.md](eval/RESULTS.md) · [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) · [docs/LEARNING.md](docs/LEARNING.md) · [DECISIONS.md](DECISIONS.md) · [CHANGELOG.md](CHANGELOG.md)

## Disclaimer

phi-guard is a portfolio and research project. It is **designed to support** privacy practices around AI use in healthcare; it does not by itself make any process compliant with PHIPA, PIPEDA, HIPAA or any other law, and it is not a medical device. Use only synthetic data unless your organization has approved the tool for real patient information.

## License

MIT. See [LICENSE](LICENSE).
