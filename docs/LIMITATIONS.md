# Limitations — what is real, what is not

Required by `PRODUCTION_EVOLUTION_PROMPT.md` §1: *"Nothing is allowed to be cosmetic
but described as real."* Anything simulated, partial, or not-yet-enforced is listed
here. Updated every phase.

Last updated: Phase 4.

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
yet.** `POST /api/mock-data` is now admin-authenticated (Phase 4) but still
unlabelled. Scheduled for the synthetic-data work in a later phase.

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

### ~~No authentication (B1)~~ — FIXED in Phase 4
Every route now requires authentication, enforced by default-deny middleware
(`src/security/`) rather than per-route decorators. `tests/unit/test_security.py`
derives the route list from the live application, so a route added later is
covered without anyone remembering. There is **no "auth off" switch**: with no
`API_KEYS` configured the server generates one temporary admin key and prints it
at startup.

**The bundled `static/index.html` does not yet send a key**, so the demo UI will
receive 401s until the Phase 6 React rebuild adds key handling. Drive the API
with `Authorization: Bearer <key>` in the meantime. This is a deliberate
trade — leaving a bypass so the old UI keeps working would have re-opened B1.

### API keys, not OIDC
§7 offers "OIDC login for humans, signed API keys or HMAC signatures for webhook
ingest — pick one and do it properly". Signed API keys were chosen: OIDC needs an
identity provider, a redirect flow, session handling and a frontend that does not
exist until Phase 6, and half an OIDC integration protects nothing. Roles are
`viewer` / `manager` / `admin`; webhook ingest authenticates by HMAC over the raw
body. Migration path: `Principal` is what the rest of the codebase depends on, so
an OIDC exchange later produces the same object from a token instead of a header.

### Rate limiting is in-process
`src/security/limits.py` holds counters in memory. With more than one worker each
holds its own, so the effective limit multiplies by the worker count. Redis is the
fix and belongs with O1.

### Idempotency covers webhook ingest only
`POST /api/ingest/webhook` honours `Idempotency-Key`. The upload, raw-paste, DB
and S3 ingest paths do not yet, so a retry there can still duplicate a week.

### CSP still allows `unsafe-inline`
The bundled UI is one 2,499-line HTML file with inline styles and scripts, so the
Content-Security-Policy cannot forbid inline execution without breaking it. A CSP
with `unsafe-inline` stops far less than it appears to. Fixed by the Phase 6
rebuild, which moves scripts and styles into separate files.

### Deferred from §7, explicitly
- **Subject-access export and delete-by-employee**: `export_subject_access_request()`
  exists in `governance/audit.py` but is not exposed on a route and there is no
  delete-by-employee operation.
- **Scheduled retention purge**: `governance/retention.py` enforces the policy
  when called; nothing calls it on a schedule.
- **Key rotation**: keys are static environment configuration. There is no
  rotation, expiry, or revocation short of redeploying.
- **Full compliance tooling**: DPIA, records of processing, and breach procedures
  are out of scope for this project.

### Integration tests excluded from CI
`tests/integration/` requires a live LLM provider and GCP credentials, so it is
marked `@pytest.mark.integration` and deselected in CI per §6.3 ("CI must never
call a real LLM"). Run locally with `pytest -m integration`. These tests currently
**fail** in this environment for that reason — they were not weakened or deleted.

### CI gate coverage is partial
CI runs lint, format, types, unit tests, `gitleaks`, the `domain` dependency
contract, the ≥95% `domain` coverage gate, and the agent eval suite (blocking).
Still to come with the phases that create what they check: the ≥80% overall
coverage ratchet, Docker/trivy, and Playwright.

### Two quality gates are in-repo, not the reference tools
The development environment has **no package-index access**, so `hypothesis`,
`pytest-cov` and `import-linter` cannot be installed. Rather than write gates that
never run, each is implemented on the standard library:

| Reference tool | Implemented as | Trade-off accepted |
|---|---|---|
| `hypothesis` | seeded generators in `tests/unit/test_domain_properties.py` | no shrinking of failing cases |
| `pytest-cov` | `scripts/domain_coverage.py` (stdlib `trace`) | line coverage only, no branch coverage |
| `import-linter` | `tests/unit/test_domain_boundary.py` (stdlib `ast`) | no layered/independence contracts, only forbidden-import |

All three are drop-in replaceable if network access returns.

---

## Statistical honesty (Phase 2)

### What is now real
Detection uses a **distributional personal baseline** (median + spread, from the
person's own earliest weeks), an effect size instead of a fixed percentage,
**CUSUM change-point detection** to separate a regime shift from a bad fortnight,
a sustained-pattern requirement, a cohort confound correction, first-class
`confidence`, and ranked per-metric `attributions`. Evidence:
`docs/PHASE2_BEFORE_AFTER.md`, generated by `scripts/phase2_before_after.py`.

### `score_range` is not a confidence interval
§6.1 asks for a confidence interval. What ships is a **heuristic band that widens
as evidence thins** — derived from how much data there is, not from a sampling
distribution, and carrying **no coverage guarantee**. It is named `score_range`
rather than `confidence_interval` deliberately: describing a rule of thumb as a
"95% CI" would borrow statistical authority the method has not earned, which is
the precise failure mode this project must not have.

### Confidence is only computed where the timeline is passed
`score_risk(..., timeline=...)` is optional. Both the CLI and the orchestrator now
pass it, but `app.py`'s inline two-week simulate route does not, and any caller
that omits it gets `Confidence.LOW` rather than a computed value. That is the safe
direction — an unknown is reported as low confidence, never as high — but it is
not the same as being measured.

### An approved schedule change is still indistinguishable from disengagement
A formally agreed move to part-time produces the same numbers as a person
disengaging, because the difference lives in an HR record this system deliberately
does not hold. No statistical method fixes this. The mitigation is that briefings
are supportive and non-disciplinary by construction, so the worst case is a
manager having a conversation they already knew the answer to. See case 5 in
`docs/PHASE2_BEFORE_AFTER.md`.

### Cohort correction is available but not wired into the entrypoints
`confirm_signals(timeline, cohort_shifts=...)` accepts the correction and it is
tested end to end, but neither entrypoint computes cohort shifts yet — doing so
requires a pass over all employees before scoring any of them, which is a pipeline
restructure belonging to Phase 5. **Until then, a team-wide event can still
produce individual signals.**

### `data_quality.low_confidence` is still not consumed
Computed at preprocessing, and still not read by the scorer. The Phase 2
confidence assessment is derived independently from the timeline. Reconciling the
two belongs with the Phase 5 API restructure.
