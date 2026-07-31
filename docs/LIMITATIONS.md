# Limitations — what is real, what is not

Required by `PRODUCTION_EVOLUTION_PROMPT.md` §1: *"Nothing is allowed to be cosmetic
but described as real."* Anything simulated, partial, or not-yet-enforced is listed
here. Updated every phase.

Last updated: Phase 0.

---

## Simulated or partial

### Ingestion sources — read paths real, two data origins synthetic
Six paths exist. The **read mechanics are genuinely real in all six** (real file
I/O, real SQLite queries, real HTTP). What differs is whether a real upstream
system is on the other end:

| Source | Read path | Upstream |
|---|---|---|
| CSV paste / upload / webhook / natural language | Real | Real — you supply the data |
| Cloud bucket (`s3_store.py`) | Real | Real S3 `GetObject` **only if** AWS credentials are configured; otherwise reads a real local folder (`data/s3_bucket/`) |
| Database (`sql_store.py`) | Real SQLite | `seed_sample_corporate_batch()` **fabricates rows** from a hardcoded employee list |

So: "six working ingestion paths" is accurate about the code; it would be
misleading to imply six live corporate systems are connected. Commit `3fde294`
first flagged this. `README.md` was corrected in Phase 0.

### Synthetic data is not labelled at row level
§5 requires every synthetic record tagged `origin='synthetic'`, a persistent UI
banner, and a production guard (`ALLOW_SYNTHETIC_DATA`). **None of this exists
yet.** `POST /api/mock-data` is unauthenticated and unlabelled. Scheduled for the
synthetic-data work in a later phase.

---

## Known gaps (not yet enforced)

### ~~`run_pipeline.py` bypassed the governance layer~~ — FIXED
The CLI now calls the same `preprocess_employee_records` the API uses, so the
allowlist, identity resolution and missing-value semantics apply to both
entrypoints. `tests/unit/test_entrypoint_parity.py` fails if the duplication
returns. Prohibited columns were also removed from `data/weekly/*.csv`, the mock
generator, the simulator input model, the webhook model, and the LLM extractor
prompt (which previously *instructed* Gemini to extract sickness data).


### Pseudonymization exists but is not the default
`identity.py` produces salted surrogate IDs, but `preprocess_employee_records`
defaults to `key_by_surrogate=False` so the demo UI keeps showing names. Must flip
to `True` before any real personal data. `IDENTITY_SALT` must also be set — without
it a development salt is used and the pseudonyms are brute-forceable.

### No authentication (B1)
Every route is public, including `POST /api/memory/clear`. Phase 4.

### Integration tests excluded from CI
`tests/integration/` requires a live LLM provider and GCP credentials, so it is
marked `@pytest.mark.integration` and deselected in CI per §6.3 ("CI must never
call a real LLM"). Run locally with `pytest -m integration`. These tests currently
**fail** in this environment for that reason — they were not weakened or deleted.

### CI gate coverage is partial
Phase 0 CI runs lint, format, types, and unit tests only. The coverage ratchet
(≥80% / ≥95% on `domain/`), `gitleaks`, import-linter contracts, Docker/trivy,
Playwright, and the agent eval gate arrive with the phases that create what they
check.

---

## Statistical honesty

The scoring logic is still **threshold-based against a single week-1 baseline**,
not the distributional/change-point method in §6.1. Consequences today: no
confidence intervals, no `insufficient_data` state propagated to briefings, no
seasonality correction, no per-metric attribution. A `data_quality.low_confidence`
flag is computed at preprocessing but is **not yet consumed** by the scorer or the
briefing. Phase 2.
