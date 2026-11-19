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
