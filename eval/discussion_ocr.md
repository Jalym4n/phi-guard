## Discussion

The OCR pipeline (Tesseract, a 3x3 median filter, automatic page layout) was chosen on dev documents and
frozen in a commit before this test run. The one later change, merging each detail's words into one black box
per line, was also made on dev data and committed before this run. Nothing was changed after seeing these numbers.

### What works well

* **Clean scans are nearly as good as typed text.** Character errors are about 0.1%, and redaction removes
  81.6% of identifiers versus 82.4% from the typed original. For a referral scanned on an office copier, the
  scan itself costs almost nothing.
* **The redacted copy of the scan is reliable.** Of the details removed from the text, 99.3% were also fully
  covered by black boxes on the scan, measured against the exact positions where each character was drawn.
  The output is image-only, so nothing hidden survives under the boxes.
* **It's fast enough:** under a second per page on a laptop CPU.

### Where it fails

* **Faxes add leaks, and bad faxes add many.** Documents with any surviving identifier rise from 24% (typed)
  to 41% on a standard fax and 77% on a bad fax.
* **Checksums turn small misreads into misses.** One misread digit makes an OHIP number, SIN or card fail its
  Luhn check, so it is no longer recognized: OHIP removal falls from 100% (typed) to 94% (fax) and 83%
  (bad fax). SINs and payment cards use the same checksum and should behave the same way, but they are too rare
  in this sample (5 and 2 examples) to measure. The checksum that protects precision on typed text works against
  recall on scans.
* **Labels get misread too.** If "MRN:" or "DOB:" is misread, the cue that triggers the detector is lost: MRN
  removal falls to 68% and date of birth to 61% on bad faxes.
* **Everything that fails on typed text still fails.** Uncued names, `29-May-1995` dates and lowercase
  addresses (the held-out template) are missed at every quality level; OCR doesn't create those failures but
  can't fix them either.

### Why

OCR errors are small on average (2% of characters even on bad faxes) but concentrated in exactly the places
that matter: digits, punctuation in numbers, and short label words. A rule-based detector is exact by design,
so a single wrong character is enough to miss an identifier.

### What would improve it

1. **Scan-aware number detection.** On OCR'd text, accept health card and SIN-shaped numbers that fail the
   checksum when they follow a cue ("OHIP", "Health card", "SIN"), marked "Please check". This needs to be
   designed on dev data and measured on a fresh test split, not tuned on this one.
2. **Fuzzy cue words** ("MRN", "DOB", "Patient") that tolerate one misread character on OCR'd text.
3. **Better image cleanup for bad faxes:** automatic deskew and adaptive thresholding before recognition.
4. **Highlight low-confidence words in the review screen**, since misread words are where leaks hide.
5. **Evaluate on real faxes** (with permission and proper safeguards). Synthetic degradation approximates fax
   artefacts but cannot reproduce real fax machines, handwriting, stamps or poor originals.
6. **Keep a human in the loop.** Studio already shows OCR confidence, the scanned pages side by side, and asks
   users to compare names and numbers before sharing. This benchmark is why that step is there.
