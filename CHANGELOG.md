# Changelog

Notable changes per unit of work. Newest first.

## Intervention outcomes + Phases 5-6 (partial)

### New: does manager action appear to help?
- `src/domain/intervention.py` records what KIND of action a manager took (closed
  list, no free text) and measures what followed in that person's own metrics.
- **Regression to the mean is corrected for, and that is the whole point.** This
  system flags people at their most extreme, so raw before/after change reports
  improvement for an intervention that did nothing — it would tell every manager
  their interventions work, be believed, and be wrong. What is reported is
  *excess* recovery: observed change minus what the person's own week-to-week
  persistence already predicted.
- Aggregation is by intervention **type**, never by manager. A per-manager
  effectiveness score makes this a performance tool whose KPI is other people's
  wellbeing metrics. A test fails if any manager-scoring function appears.
- Every outcome is permanently `association_only`; the model is frozen so a
  consumer cannot strip the caveat before rendering.
- **Not built**: analysing what a manager *said*. That needs the contents of a
  private 1-on-1. Reasoning is at the top of `src/domain/intervention.py`.

### Phase 5 (partial) — API restructure
- `src/api/errors.py`: RFC 9457 problem+json on every error, with a correlation
  ID. An unhandled exception returns an opaque message — traces here contain
  employee names, so one reaching a browser is a privacy incident, not a bug.
- `src/api/routers/evolution.py`: first extracted router. Mounted at `/api/v1`
  (the versioned contract) and at `/api` as a hidden alias so nothing breaks.
- `scripts/export_openapi.py` exports the schema in CI rather than committing
  it, so the generated frontend types cannot drift from what is served.
- **Still to do**: the other ~28 routes remain in `app.py`. It is not yet a
  composition root and is still over 400 lines.

### Phase 6 (partial) — React frontend
- `frontend/`: React 18 + TypeScript (strict) + Vite + TanStack Query + Router.
- **The UI works again.** Phase 4 left the old dashboard receiving 401s;
  `ApiKeyGate` prompts for a key, holds it in sessionStorage (dies with the tab),
  and a 401 clears it and re-prompts instead of hanging on a loading state.
- Diagnostic Room migrated first, per §9's prescribed order. At low confidence
  the score is **not rendered as a number at all** — a range and the caveat get
  equal visual weight, because "6/10" in large type with grey caveat text
  communicates only the first.
- 9 vitest tests including a `jest-axe` accessibility assertion; `tsc` strict and
  `npm test` wired into CI as a separate job.
- **Still to do**: Console, History and Home pages; generated API client;
  Playwright E2E.

### Fixed
- **The audit log had silently stopped recording.** `CREATE TABLE IF NOT EXISTS`
  does nothing to an existing table, so the Phase 4 hash columns were never added
  to an existing `audit.db` and every write failed on the missing column —
  silently, because `record_access()` swallows exceptions by design. Found by
  running the app, not by a test: the tests all used fresh temporary databases.
  Migration added, plus a regression test that builds a legacy-shaped log.
- `verify_chain()` now distinguishes pre-chain rows (unverifiable) from a hash
  removed after chaining began (tampering).

## Phase 4 (complete) — security baseline

- **Blocker B1 closed.** Every route requires authentication, enforced by
  default-deny middleware (`src/security/`), not per-route decorators. B1 exists
  because `POST /api/memory/clear` wiped all data unauthenticated — not because
  anyone decided it should be open, but because nothing forced the question.
  A new route is protected the moment it exists; making it public is a visible
  edit to `policy.py`.
- **Signed API keys, not OIDC**, with a written rationale and migration path.
  Roles `viewer` / `manager` / `admin`; only hashes are stored; comparison is
  constant-time and does not return early. Webhook ingest authenticates by HMAC
  over the raw body, so a captured request cannot be replayed with new contents.
- **No "auth off" switch.** With no `API_KEYS` set the server generates one
  ephemeral admin key and prints it loudly at startup. A bypass flag for local
  convenience is exactly the flag that ends up set in a deployment.
- **Rate limiting** per identity *and* per IP, with a tighter budget on
  LLM-triggering routes — an unauthenticated flood against `/api/run` would
  previously have burned the project's API quota and its owner's money. Sliding
  window, so a caller cannot send two full budgets across a boundary.
- **Body size cap** checked before the body is read; **idempotency keys** on
  webhook ingest, because a sender that times out and retries would otherwise
  silently double one person's metrics.
- **Security headers + CSP** on every response, including error responses.
- **Audit log is now hash-chained** with `verify_chain()`. The append-only
  triggers only protect the log from code using this module; anyone with the
  file can rewrite it. The chain makes that detectable, which is what
  "tamper-evident" actually means.
- **`gitleaks` in CI** with full history. B8 was logged as "secrets in-repo";
  the audit found `.env` gitignored with zero commits in history, so the real
  gap was the absence of scanning.
- Security suite derives the mutating-route list from the live app, so a route
  added later is covered without anyone remembering to add it.
- Found by the new tests: `IdempotencyStore` evicted before inserting, so it
  could sit one entry over its cap. "Bounded" that is off by one is not bounded.
- **Known consequence**: the bundled `static/index.html` does not send a key and
  will now receive 401s until the Phase 6 rebuild. Recorded in
  `docs/LIMITATIONS.md` — leaving a bypass so the old UI kept working would have
  re-opened B1.

## Phase 3 (complete) — Intelligence II: agent evolution

- **Manager feedback capture** (`src/domain/feedback.py`, `src/evolution/feedback_store.py`,
  `POST /api/feedback`). This is the ground-truth signal the system has never
  had: until now it produced judgements about people and never once found out
  whether any were right. `harmful` is a separate axis from `not_accurate` — a
  briefing can be perfectly accurate and still have damaged someone, and
  collapsing them would let the headline metric improve while harm rose.
- **No free-text field anywhere in the feedback path.** A notes box on a form
  about an employee is where health details and character judgements end up. The
  SQLite schema has no column for it, and a test fails if one is added.
- **Versioned model registry with an asymmetric promotion gate**
  (`src/evolution/registry.py`). Never promote an unevaluated model, never
  promote on a held-out set under 10, and *any* increase in harm blocks
  promotion however much precision improved. Automatic rollback when live
  calibration regresses against the version's own held-out evidence.
- **Every prediction records `model_version` and `provenance`.** Degraded results
  are labelled `degraded: true` with `confidence: low` — a local-ML guess and a
  Gemini assessment are indistinguishable once both are a number in a JSON file.
- **Compounding memory** (`src/domain/continuity.py`): week 8's briefing carries
  what was raised in week 3, what the manager said back, and whether things have
  improved since. Behavioural only — week numbers, scores, classifications,
  signal names. A test asserts the summary leaks no personal content.
- **Self-critique before the punitive-language validator**
  (`src/domain/critique.py`). Catches what a deny-list structurally cannot: a
  verdict on someone's inner state, a conclusion the evidence doesn't support, a
  fabricated second signal, a missing low-confidence caveat, a surname leak.
  Blocking findings map onto CONTEXT.md rules and are not traded off.
- **Calibration monitoring** (`src/evolution/calibration.py`, `GET /api/calibration`):
  lifetime vs recent, so a system that was accurate for six months and wrong for
  three weeks shows as drift rather than being averaged into a comfortable
  figure. Says plainly when there is not enough feedback to tell.
- **Agent eval suite is BLOCKING in CI** (`scripts/agent_eval.py`,
  `tests/eval/golden_set.json`). 9 accuracy + 6 safety cases through the real
  domain logic with the deterministic fake — no LLM, so §6.3 holds. A safety
  failure fails the build regardless of the accuracy score.
- Found by the new tests: an adverb defeated the mind-reading check. A model
  writes "has clearly become disengaged", not "is disengaged", and the hedged
  phrasing is the one a manager is most likely to believe.

## Phase 2 (complete) — Intelligence I: honest statistics

- **Personal baselines are now distributions, not a single week.** `median` for
  the centre, and for spread the larger of MAD and the median successive
  difference. Week 1 was one observation: anyone whose first week was unusually
  productive had their personal best used as their baseline, so every ordinary
  week afterwards read as decline.
- **Effect size replaces the fixed percentage cut-offs.** A deviation must be
  both unusual *for that person* and materially large. Either test alone has a
  failure mode that harms somebody: effect size alone flags a rock-steady person
  for a trivial wobble; percentage alone flags a naturally variable person for an
  ordinary week.
- **CUSUM change-point detection** (`src/domain/changepoint.py`) separates a
  genuine regime shift from a bad fortnight. The 2+-consecutive-week rule is kept
  as a floor. A single extreme week can no longer cross the threshold on its own.
- **A resolved pattern is no longer reported as current risk.** A decline that
  ended two weeks ago is carried by the history and recurrence machinery; this
  week's assessment describes this week.
- **Cohort confound removal** (`src/domain/cohort.py`) as a fairness correction
  only: one shared number per week, never a per-person comparison, only downward
  moves, and structurally unable to create a signal. A test fails if any
  ranking-shaped function appears in the module.
- **Uncertainty is first-class** (`src/domain/uncertainty.py`): `confidence`,
  `score_range` and `insufficient_data` travel with every score, and low
  confidence is stated in the rationale rather than only in a field a consumer
  might not read. `score_range` is a heuristic band, **not** a confidence
  interval — named and documented accordingly.
- **Per-metric attribution** (`src/domain/attribution.py`) derived from the same
  weights the score uses, so the explanation cannot drift from the number.
- `score_risk()` and the `RiskScorer` Protocol accept the timeline; the CLI and
  orchestrator pass it.
- **Evidence, not claims**: `scripts/phase2_before_after.py` runs both methods on
  the same fixtures and generates `docs/PHASE2_BEFORE_AFTER.md`. Headline result —
  a rough fortnight followed by full recovery went from **three confirmed signals
  to none**, while genuine sustained and abrupt declines are still caught.
- The before/after script caught a Phase 2 regression before it shipped: MAD over
  three alternating values collapses to ~1, and the first draft flagged a
  naturally variable worker. That is why `build_baseline` takes the larger of the
  two spread estimates.
- `src/domain` is at **100%** line coverage (756/756) against the 95% gate.

## Phase 1 (complete) — extract the domain

- Add agent `Protocol`s (`src/domain/protocols.py`) and deterministic fakes
  (`src/domain/fakes.py`). `detect_trends()` and `score_risk()` gained optional
  injection points; every production path still defaults to the LLM.
- Add the parity proof (`tests/unit/test_pipeline_parity.py`): the CLI and the
  API path are run over the same fixture with the fakes injected and their
  stored evaluations compared week by week. Blocker B6 now fails a test.
- Add property tests (`tests/unit/test_domain_properties.py`): bounds,
  monotonicity, idempotence, decay, the 2+-consecutive-week rule, and the
  fairness property that detection is invariant to an employee's absolute level.
- Add the §4 dependency contract (`tests/unit/test_domain_boundary.py`) and the
  §8.3 coverage gate (`scripts/domain_coverage.py`), both wired into CI.
  `src/domain` is at **100%** line coverage against a 95% gate.
- **Fix: `healthy_streak_from()` double-counted.** It added each history
  record's own stored `healthy_streak` on top of the run it had already walked,
  so two genuine healthy weeks reported three and the recurrence bonus decayed
  after 3 weeks instead of the documented `HEALTHY_DECAY_WEEKS = 4`. Found by
  the decay property test. **This changes scores**: recovering employees now
  carry the +1 recurrence adjustment for one week longer, which is what the
  documented rule always said.
- **Fix: `src/__init__.py` eagerly imported the whole agent stack.** A plain
  `from .agent import app` meant importing the deliberately pure `src.domain`
  first pulled in `google.adk`, `google.genai`, `fastapi`, `starlette` and
  `dotenv`. Now exported lazily via PEP 562; the boundary test fails if it
  regresses.
- No new dependencies. `hypothesis`, `pytest-cov` and `import-linter` are the
  reference tools for the three gates above but cannot be installed here (no
  package-index access), so each is implemented on the standard library —
  seeded generators, `ast`, and `trace` respectively.

## Phase 1 (earlier work)

- Add `src/domain/`: pure decision logic with Pydantic v2 models, no I/O, no LLM,
  no framework imports. `models.py`, `signals.py`, `risk.py`.
- Move signal detection out of `trend_detector_agent.py` and the score bands,
  recurrence bonus and healthy-streak decay out of `risk_scorer_agent.py`. Both
  agents now delegate; their public signatures are unchanged so every existing
  caller and test is untouched.
- Add `compute_risk_index()` — a deterministic scorer that did not previously
  exist, since the LLM produces the score today. Written additively and **not
  wired in**, so this phase changes no behaviour.
- Fix a shadowing bug caught by `ty`: the local `apply_recurrence_bonus` bool
  shadowed the imported function of the same name, which would have raised
  `TypeError` at runtime.


## Phase 0 — Close the governance bypass

- Point `run_pipeline.py` at the shared `preprocess_employee_records` instead of
  its own inline CSV parser. The CLI previously bypassed every governance control:
  it read `sick_days` (health data), keyed identity on first name, and defaulted
  missing metrics to `0`.
- Remove prohibited columns from `data/weekly/*.csv` and `data/realtime/*.csv`,
  the mock generator, the simulator input model, and the webhook input model.
- Stop the LLM extractor prompt from instructing Gemini to extract sickness,
  absence, mood and quality ratings; it is now told explicitly never to emit them,
  and to omit a key rather than invent a value.
- Move `sys.stdout` UTF-8 rewrapping in `run_pipeline.py` behind `__main__` — an
  import-time side effect that replaced the streams for anything importing it.
- Add `tests/unit/test_entrypoint_parity.py` so the duplication cannot return.

## Phase 0 — Stabilise

- Add CI (`.github/workflows/ci.yml`): ruff check, ruff format, `ty`, unit tests on
  every push and PR, installed from the lockfile with `uv sync --frozen`.
- Mark `tests/integration/` as `@pytest.mark.integration` and exclude it from CI —
  it requires a live LLM provider and GCP credentials (§6.3).
- Fix `ty` error in `governance/notice.py`: iterate `PermittedUse.__members__`.
- Apply `ruff format` across the tree (18 files).
- Add `docs/LIMITATIONS.md` recording every simulated or unenforced path.
- Correct three README claims that overstated ingestion sources as "genuinely
  working / not demo stubs" (B11).
- Add `PROGRESS.md` and this file.

## Pre-Phase-0 (committed during Phase 0 tree cleanup)

- **Governance package** (`src/governance/`): default-deny data allowlist enforced
  at ingest, purpose binding that refuses punitive uses in code, append-only audit
  log with DB-enforced immutability, retention with verified real deletion, and a
  notice artifact generated from the allowlist so it cannot drift.
- **Removed prohibited fields** from the API ingest path: `sick_days` (health data,
  GDPR Art. 9 / ADA), `sentiment` (emotion inference, EU AI Act Art. 5),
  `task_accuracy` (performance metric in a support tool).
- **Replaced absolute thresholds with personal deviation** in trend detection —
  absolute floors flagged part-time and phased-return schedules as disengagement.
- **Identity resolution + pseudonymization** (`data_layer/identity.py`): salted
  surrogate IDs, employee-ID and alias support so a rename keeps its history, and
  name normalisation covering casing, accents, honorifics, and `"Last, First"`.
  Fixes distinct people merging and one person splitting across spelling variants.
- **Tolerant value coercion** (`data_layer/coercion.py`): missing stays missing
  instead of defaulting to `0`/`40`, unit normalisation (`"90 min"` → 1.5h),
  implausible values rejected with a reason, and a per-record completeness summary.
- **Week-number bounds** at every ingestion entry point; a CSV cell can no longer
  create `week-5.csv` or corrupt baseline-relative scoring.
- **Atomic pipeline-slot reservation** — check-then-start let concurrent requests
  launch multiple runs against the same memory files.
- **Locked, atomic API metrics** — the previous read-modify-write lost counts and
  could leave truncated JSON.
- **Multi-provider LLM fallback**: Gemini → Groq → Ollama → local ML, with
  provider-aware error handling so one bad credential no longer kills the chain.
- Fix `.env` never loading under `uvicorn app:app` — the server had been running
  with no API keys at all, silently using local fallbacks for every request.
