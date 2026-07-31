# Security Policy

## Status: not production-ready

This project is under active redevelopment toward production use. **It currently
has no authentication** — every route is public, including destructive ones. Do
not deploy it anywhere reachable, and do not point it at real employee data. See
`docs/LIMITATIONS.md` for the full, current list of gaps.

## Reporting a vulnerability

Please report privately via [GitHub Security Advisories][advisories] rather than a
public issue. Include what you did, what happened, and the impact. Expect an
acknowledgement within a few days; this is a solo-maintained project, so please be
patient with fixes.

[advisories]: https://github.com/Athish2002/quiet-quitting-detector/security/advisories/new

## In scope

- Authentication and authorization bypass
- Anything that lets prohibited data (health, message content, telemetry,
  protected characteristics) reach storage — see `config/data_allowlist.json`
- Bypassing purpose binding to obtain scores for a forbidden use
  (`src/governance/purpose.py`)
- Audit log tampering or omission
- Injection, SSRF, path traversal, stored XSS in briefing rendering
- De-anonymising a pseudonymous surrogate ID

## Privacy issues count as security issues

This system processes behavioural data about people. **A privacy defect is a
security defect here**, and is treated with the same severity. If you find a way
to make the tool reveal, infer, or retain something it promises not to — or to
produce output usable for a punitive employment decision — report it.

## Known and already documented

Please don't report these; they're tracked:

- No authentication on any route (Phase 4)
- Synthetic data is not row-tagged and `POST /api/mock-data` is unprotected
- Pseudonymization exists but is off by default (`key_by_surrogate=False`)
- No rate limiting or idempotency on ingest

## Secrets

If you believe a credential was ever committed, report it privately and do not
open a public issue. `.env` is gitignored and history has been checked, but say so
if you find otherwise.
