# Threat model (v0.1)

**Asset:** patient identifiers in clinical text sent to AI tools.

| Threat | Mitigation |
|---|---|
| Identifiers leak to a third-party model | Regex detectors + Luhn validation; redaction before sending |
| Tokens reversed by an attacker | HMAC-SHA256 with a secret key; vault is in memory only |
| Indirect prompt injection in documents | Heuristic screening; `wrap_untrusted()` fencing |
| Audit log edited after the fact | SHA-256 hash chain; `verify()` |
| PHI written to logs | Audit entries store counts only |
