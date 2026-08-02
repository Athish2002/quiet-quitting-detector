# Limitations — what is real, what is not

Required by `PRODUCTION_EVOLUTION_PROMPT.md` §1: *"Nothing is allowed to be cosmetic
but described as real."* Anything simulated, partial, or not-yet-enforced is listed
here. Updated every phase.

Last updated: Phases 0-6 complete.

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
yet.** `POST /api/mock-data` is admin-authenticated (Phase 4) and now
**reproducible** — seeded, so the same seed gives byte-identical output — but it
is still unlabelled, and nothing stops a production build from seeding.

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

The `frontend/` SPA handles keys (`ApiKeyGate`) and all four pages are migrated.
The legacy `static/index.html` was retired in Phase 6.

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

### ~~Idempotency covers three of five ingest paths~~ — FIXED
All six ingest paths honour `Idempotency-Key` now. Enforced by a test that
derives the route list from the live app, so a path added later is covered
without anyone remembering.

### Rate limits are three fixed numbers
300/min for reads, 30/min for writes, 6/min for LLM-triggering routes. The single
30/min bucket that preceded them broke ordinary dashboard use — found by the E2E
suite, where a different test failed on each run. They are still guesses tuned to
one operator, not measured against real traffic.

### CSP allows inline STYLE, not inline script
`script-src 'self'` since Phase 6 retired the inline-script dashboard.
`style-src` still allows `'unsafe-inline'` because React sets element styles
directly (sparkline bar heights); removing it needs a nonce plumbed through every
render. Injected CSS is a far narrower problem than injected script.

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

### The ADK server app needs GCP credentials to import
`src/fast_api_app.py` calls `google.auth.default()` and constructs a Cloud
Logging client at import time, so it cannot start without credentials. That is
why `tests/integration/test_server_e2e.py` cannot run here. The agent itself has
no such dependency — `tests/unit/test_agent_tools.py` asserts that `src.agent`
and `src.orchestrator_agent` import cleanly without them.

### Integration tests excluded from CI
`tests/integration/` requires a live LLM provider and GCP credentials, so it is
marked `@pytest.mark.integration` and deselected in CI per §6.3 ("CI must never
call a real LLM"). Run locally with `pytest -m integration`. These tests currently
**fail** in this environment for that reason — they were not weakened or deleted.

### CI gate coverage
CI runs lint, format, types, unit tests, `gitleaks`, the `domain` dependency
contract, the ≥95% `domain` coverage gate, the blocking agent eval suite, the
frontend (`tsc` strict + vitest + axe), and Playwright E2E against the composed
stack. **Still missing**: the ≥80% overall coverage ratchet (only `domain` is
gated) and the Docker build + `trivy` scan.

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


---

## Intervention outcomes (new)

### It measures association, never causation
`src/domain/intervention.py` reports what followed a manager's action. There is
no control group and no randomisation — the "treatment" is assigned to whoever
looked worst — so nothing here is evidence that an action *caused* an outcome.
Every record carries `association_only: true` on a frozen model so a consumer
cannot strip it, and the UI leads with the caveat rather than footnoting it.

### Regression to the mean is corrected for, imperfectly
People are flagged at their most extreme, so they tend to improve regardless.
The correction estimates each person's own lag-1 persistence and subtracts the
recovery that predicts. That is far better than raw before/after, and it is
still a single-parameter model of a messy process: it assumes persistence is
stable over the window and estimates it from as few as four points. Treat
"excess recovery" as a rough filter for "was this more than nothing", not as an
effect size.

### There is deliberately no per-manager view
No `manager_id` column, no scoring function, and a test that fails if one
appears. A per-manager effectiveness number turns this into a performance tool
whose KPI is other people's wellbeing metrics, which creates an immediate
incentive to lean on whoever's numbers look bad.

### What was asked for and not built
Determining whether a manager's *words* affected an employee. That requires
capturing what was said in a private conversation — prohibited by CONTEXT.md
rule 5, and a categorical escalation from counting tasks to listening to
meetings. The reasoning is at the top of `src/domain/intervention.py`.

---

## API restructure (Phase 5, complete)

`app.py` is a 155-line composition root; all routes live in `src/api/routers/`.
Enforced by `tests/unit/test_structure.py`.

**Two legacy files are still over 400 lines** and sit on an explicit exception
list that can only shrink (a test fails if either grows):

| File | Lines | Why it is still there |
|---|---|---|
| `src/risk_scorer_agent.py` | 612 | Prompt, provider chain, nearest-neighbour matcher and local-ML predictor in one module. The fallback tiers want their own. |
| `run_pipeline.py` | 553 | CLI presentation. Wants a `src/cli/` package separating rendering from driving. |
| `src/app_utils/runner_helper.py` | 493 | Monkey-patches the GenAI client constructor (B9). Wants the patching split from the chain. |

**Config is still not a validated `Settings` model.** §4 wants every setting read
through a Pydantic model that fails fast on bad values; `src/api/paths.py` is
plain constants and env vars are read ad hoc across modules. Doing it half would
leave two config mechanisms instead of one.

## Frontend (Phase 6, complete)

All four pages migrated; `static/index.html` retired; Playwright E2E runs against
the composed stack in CI; `tsc` strict and axe both clean.

### Generated types cover requests, not responses
`schema.ts` is generated from the running app's OpenAPI, so **paths, methods and
request bodies** fail `tsc` when the backend changes them. Response *fields* are
not covered: the handlers are annotated `-> dict`, so the schema types their
responses as an open object. Closing that means adding `response_model=` to every
handler — worth doing, not yet done. The response interfaces in
`frontend/src/api/types.ts` are hand-written until then.

### Styling is plain CSS, not Tailwind
§4 names Tailwind. At four pages of semantic HTML a utility framework adds a
build step and a class-soup diff for no benefit. Revisit when the component count
justifies it.

### The build output is not committed
`frontend/dist` is gitignored, so a fresh clone serves a "build the interface"
message until `npm --prefix frontend run build` has run. Normal for an SPA, and
stated rather than left to be discovered.
