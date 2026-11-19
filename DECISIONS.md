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
