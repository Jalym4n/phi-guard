# phi-guard

Redact patient data and screen for prompt injection before text reaches an AI model.

`phi-guard` is a small, dependency-free Python library and CLI:

- **PHI/PII detection** for 10 Canadian identifier types (OHIP, SIN, cards, email, phone, postal code, date of birth, MRN, patient name, IP address), with Luhn checksum validation.
- **Reversible pseudonymization** with HMAC-SHA256 tokens (`[SIN_2311c0d1]`) or permanent masking (`[SIN]`).
- **Prompt-injection screening** with Unicode normalization, zero-width detection, and Base64 decoding.
- **Tamper-evident audit log** with a SHA-256 hash chain.

```bash
pip install -e .
phi-guard redact examples/sample_note.txt
phi-guard inject examples/poisoned_doc.txt
```

All example data is synthetic. See `docs/THREAT_MODEL.md`.
