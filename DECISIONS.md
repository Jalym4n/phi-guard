# Design decisions

A running log of choices made while building v0.2, with the reason for each.
Newest entries are added at the end of each section.

## Project baseline

**D1. The v0.1 code was reconstructed from the spec.** The repository contained only a one-line README
when v0.2 work started. The v0.1 package (`detectors`, `redactor`, `injection`, `audit`, `guard`, `cli`,
29 tests, CI, examples) was rebuilt from the spec's description and committed and tagged `v0.1.0` as its
own commit, so it can be compared with (or replaced by) any original copy.

## Core library

**D2. `Finding` moved to `finding.py`.** Address, dictionary, and NER modules all produce findings; a
shared module avoids circular imports. `phi_guard.detectors.Finding` is still re-exported.

**D3. Confidence is a fixed per-detector estimate, not a probability.** Checksum-validated numbers
(SIN, OHIP, cards) get 0.99, email 0.98, context-cued patterns 0.9, labelled names 0.85, honorific
names 0.8, addresses 0.85, NER 0.7, custom terms and manual selections 1.0. The UI marks anything
under 0.85 "Please check". The benchmark measures real precision per type; these values are ordered
to match it, not fitted to it.

**D4. Undecided findings are removed.** `Redactor.redact(keep=...)` takes the spans to *keep*. Anything
the client did not explicitly keep is redacted, so a buggy or stale client fails safe.

**D5. Manual selections beat every detector.** A manual span wins any overlap (priority 200) and cannot
be "kept". Custom always-remove terms come next (110).

**D6. Never-remove terms are applied before overlap resolution**, so a lower-priority finding hidden
under a suppressed one can still be reported. Digit-heavy terms compare digits only, so a clinic phone
number matches whatever formatting it appears in.

**D7. SINs starting with 0 or 8 are rejected.** Those ranges are not issued to individuals; rejecting them
cuts false positives from 9-digit order numbers.

**D8. Document type is decided by content (magic bytes), and must agree with the extension.** A renamed
executable or a ZIP renamed `.docx` is rejected with a plain-language message.

**D9. .docx headers and footers are scanned.** Letterhead and footers often carry patient names. They are
extracted (header first, footer last) and redacted in the output copy.

**D10. Redacted .docx output simplifies formatting only inside changed paragraphs.** Paragraph and table
structure is preserved; within a paragraph that contained patient details, all text takes the first
run's formatting. Untouched paragraphs keep their formatting exactly.

**D11. PDFs are redacted to .txt.** Rewriting text inside a PDF safely (without leaving the original text
in the content stream) needs a heavier toolchain. Batch output for a PDF is a `.txt`; this is stated in
the UI and README.

**D12. Batch summary CSV escapes formula-like cells** (`=`, `+`, `-`, `@`) to prevent CSV injection when the
sheet is opened in a spreadsheet.

**D13. Injection findings report offsets in the original text.** Normalization (NFKC, zero-width removal)
changes string length, so `normalize_with_map` keeps a per-character origin map for highlighting.

## Evaluation

**D14. Gold labels follow a "patient and relatives" scope** (as in HIPAA Safe Harbor). Clinician names are
marked `ignore`: a system that removes them is neither rewarded nor penalized. The clinic's own phone, fax,
address and postal code are deliberately *unlabelled* hard negatives.

**D15. Dev and test splits use different seeds; the test split also has held-out templates.** Because the
same person wrote the generator and the rules, a test split from the same templates would only measure
how well the rules fit their author's own phrasing. 20% of test documents use a nursing-handover template,
and about 30% of test injection snippets use phrasings, that never appear in dev. Results are reported for
seen and held-out templates separately.

**D16. Rules were frozen in a commit before the first test run** ("Freeze detection and injection rules
before first test-split run"). All rule changes in v0.2 were driven by dev-split errors only.

**D17. Presidio runs out of the box with spaCy `en_core_web_lg`**, its recommended model, so the baseline is
not handicapped by a small model. Overlapping Presidio results are resolved by score then length (the same
rule its anonymizer uses) so duplicates are not double-counted. Presidio could be extended with Canadian
recognizers; the comparison is explicitly against the default configuration.

**D18. Leakage counts characters, not types.** A document leaks if any character of any labelled identifier
is left uncovered by any prediction, whatever label the system used. This is what matters for privacy;
type mistakes are measured separately by per-type F1.

**D19. Chart colours come from a validated categorical palette** (adjacent-pair colour-vision-deficiency
separation checked), with at most three series per chart, a legend for multi-series charts, and text in ink
colours rather than series colours.

**D20. One detector change after the freeze, with zero effect on reported numbers.** A Studio API test found
that the labelled-name cue (`Patient:` etc.) used `\s*`, which could cross a line break and grab the next
line's label as a name. It was changed to same-line whitespace. The benchmark was re-run: every precision,
recall, F1 and leakage figure on the test split was identical, so RESULTS.md was not regenerated.

## Studio backend

**D21. The session token travels in the URL fragment** (`#token=...`). Fragments are never sent to the server
or written to server logs; the page reads it, keeps it in memory, and removes it from the address bar.

**D22. Uploads are kept in memory.** Starlette spools multipart files larger than 1 MB to a temporary file on
disk. Studio raises that limit to the configured upload ceiling, and a test fails if any temporary file is
created while uploading a 5 MB document.

**D23. File names are never written to the activity log.** Names like `Whitfield_E_referral.docx` are patient
details. The log records the file type and size only. (Batch `summary.csv` does list file names: it is a file
the user explicitly downloads, alongside the redacted files themselves.)

**D24. Batch upload paths are sanitized** (no `..`, drive letters or absolute paths) to prevent "zip slip" when
the user extracts the result ZIP.

**D25. Keychain fallback is an obfuscated file, labelled as such.** Without an OS keychain there is no secret to
protect the key with, so the fallback file is AES-GCM-encrypted under a key derived from machine identity and
user name (scrypt), with 0600 permissions. It stops casual copying to another machine, not an attacker running
as the same user. Settings says "Stored in a protected file (less secure than the system keychain)".

**D26. Key export uses scrypt (n=2^15, r=8, p=1) + AES-256-GCM** with a random salt and nonce, and a minimum
password length of 10. Import refuses absurd scrypt parameters so a crafted file cannot cause a CPU/memory DoS.

**D27. Live preview calls are not logged.** `/api/redact` writes an activity entry only when `final=true`
(Copy or Download), so toggling Keep/Remove does not flood the log.

**D28. Polling `/api/session` does not count as activity**, so the idle countdown is not reset by the page
that displays it.

**D29. Unexpected errors return a generic message.** Exception text could contain patient details, so it is
never echoed to the browser.
