# Phase 7 — Security Scanner Verification

## Implemented

- Persistent security scan and finding models.
- Alembic migration `e7f1a2b3c4d5` chained after Phase 5.
- Static repository scanner with conservative rules for:
  - hardcoded credentials
  - private key material
  - AWS access-key patterns
  - dynamic code execution
  - shell command execution
  - potential SQL string interpolation
  - unsafe pickle deserialization
  - weak MD5/SHA-1 hashing
  - disabled TLS verification
  - debug mode
  - unsafe YAML loading
- Secret evidence is redacted before persistence/return.
- Findings contain rule, category, severity, file, line, evidence, confidence, and remediation.
- Background scan endpoint and latest-scan/findings/summary APIs.
- Repository isolation is enforced by repository ID on persisted findings.

## Endpoints

- `POST /api/v1/repos/{repo_id}/security/scan`
- `GET /api/v1/repos/{repo_id}/security/scans/latest`
- `GET /api/v1/repos/{repo_id}/security/findings`
- `GET /api/v1/repos/{repo_id}/security/summary`

## Verified in this environment

- `python -m compileall -q app tests` — passed.
- Direct security scanner smoke test — passed.
- Credential evidence redaction — passed.
- Command execution detection — passed.
- Unsafe pickle detection — passed.
- Weak hash detection — passed.
- Alembic revision chain inspected; Phase 7 correctly follows Phase 5.

## Not fully verified here

The complete pytest suite could not be collected because the execution environment is missing the existing `tree_sitter` dependency required by the Phase 1–6 test application import path. No full-suite pass count is claimed.

The scanner itself was tested independently without importing the full FastAPI application.

## Scope / honesty

This is static heuristic security analysis. It does **not** claim to prove exploitability, discover every vulnerability, or provide CVE/dependency vulnerability intelligence. No external vulnerability database is bundled or queried.

Repository source is treated as untrusted data. Findings never include the original credential value when a secret rule matches.

## Known limitations

- No dependency CVE database yet.
- No taint/data-flow analysis.
- Some findings are intentionally conservative and require human review.
- The scan currently analyzes text files recognized by the repository scanner.
