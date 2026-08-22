# Changelog

Notable changes per unit of work. Newest first.

## Redesign S4 — Cohort section, deviation bars, and unranked team grid

Replaced `Console.tsx` at route `/cohort` with the Modernist Cohort section (`frontend/src/pages/Cohort.tsx`).

**Cohort grid & Deviation bars:**
- Section Header with eyebrow `"COHORT"`, title `"Full team telemetry, evaluated against each person's own baseline."`, and explicit reminder that comparing people to each other is refused.
- Two-column alphabetical grid over a `1px` rule gap. Each cell links to `/person/${name}`.
- **Strictly unranked**: no sort control, no leaderboard affordance, no ordering by score.
- **Four deviation bars** per card on a `126px 1fr 1fr 62px` grid with a `2px var(--muted)` centre axis:
  - Tasks completed, Response time, Weekly hours, After-hours logins.
  - Negative values fill right-to-left against centre; positive values fill left-to-right.
  - Adverse deltas render in `var(--accent)` with `var(--ink)` text; non-adverse deltas render in `var(--rule)` with `var(--muted)` text.
  - After-hours logins carry no risk weight and are strictly inert across all values.
- **Empty state**: bordered panel directing operators to `/ingest`.

**History & Scaffolding Polish:**
- Modernized History trajectory bars on a clean grid and restyled operational event log.
- Removed unwanted outline boxes on placeholder scaffolding.

**Tests & Accessibility:**
- Added `frontend/src/pages/Cohort.test.tsx` asserting alphabetical sorting, absence of sort controls, adverse/inert bar coloring, empty state navigation, and zero axe accessibility violations. All 95 frontend tests passing.

## Redesign S3 — Overview section, R2 side panels, and the Modernist button system

Replaced `Home.tsx` with the Modernist Overview section at `/` (`design/REDESIGN_PLAN.md`).

**Overview layout & R2 panels.**
- `SectionHeader` with `wide={true}` (44px h1 capped at 16ch), eyebrow `"OVERVIEW"`, title `"Weekly telemetry, read against a person's own history."`
- Bespoke hero layout resolving R2: on wide screens, the empty right-hand space beside the hero holds:
  1. A **band-distribution block**: decomposes "currently raised above Healthy" into four rows with classification chips (Healthy, Watch, At Risk, Silent Exit). Shows COUNTS ONLY — never names, never sorted by score.
  2. A **latest evaluation panel**: reports how many were evaluated, the latest telemetry week, and data gaps. Deliberately does not repeat the active model name, which the sidebar owns.
- **4-column stat strip**: `People on record` / `Currently raised above Healthy` / `Manager verdicts recorded` / `Reported as harmful` on equal columns with 1px rules between and 2px rule under. All four numerals are `var(--ink)` with no exceptions — a headcount of people is never rendered in an alert color.
- **"What this is, and what it is not"**: two columns split by a 1px rule, headed by uppercase accent labels "It does" / "It does not" over ethical safeguards copy, a 2px rule, and a closing caveat paragraph.
- **Three link cards**: Cohort (`/cohort`), Diagnostic room (`/diagnostic`), Access trail (`/audit`) with surface background, 1px rule, and accent hover states.
- **Empty state handling**: when no telemetry or verdicts exist, numerals read 0/— and an accent notice explains no manager has validated the system yet.

**Shared Modernist button system & classification chips.**
- Introduced `.btn`, `.btn--primary` (accent fill, surface text, hover `--accent-hover`, active `--accent-active`), `.btn--secondary` (transparent, 1px rule border), `.btn--quiet`, and `.btn--danger` scoped under `.app-shell`.
- Added `.chip` and `.chip--healthy` / `--watch` / `--at-risk` / `--exit` matching dual-theme verified contrast pairs.

**Tests & Accessibility.**
- Added `frontend/src/pages/Home.test.tsx` covering populated state, empty state, ink numeral constraint, absence of sort controls, counts-only distribution, and zero axe accessibility violations. All 89 frontend tests pass.

## Redesign S2 — one shell, eight sections, and the model chain on show

The four sibling pages become a single shell: a 244px sticky sidebar, eight
sections on real routes, and three global banners. The existing pages are
mounted at their new addresses unchanged, so the app stays usable at every
commit rather than going dark for nine sessions. `/console` is now `/cohort`.

**The provider-call meter is gone (R1).** The prototype showed "128 / 500" and
"Quota resets Monday 00:00 UTC". This system runs on a chain of ten free models
with a local fallback and imposes no hard limit, so that bar would have drawn a
constraint that does not exist. What replaced it is the thing an operator
actually needs when output looks wrong: which model answered, and what is left
behind it. The full chain sits in a `<details>` disclosure, each entry marked
*in use*, *ready*, or *exhausted* with its cooldown — built on `ProviderStatus`,
which already carried `fallback_sequence` and `exhausted_models` and had never
been shown. Native `<details>` rather than a custom menu: keyboard operable and
labelled for free, and a dropdown with no state cannot get stuck open.

**The demo-state toggle is gone too.** Empty and degraded are what the API
returns, not states an operator switches into.

Person detail is the one nav item with no fixed destination. Opening an
assessment is written to the access trail, so it should never be somewhere you
land by clicking a nav item — it is reached from the cohort, by choosing a
person. Until then the item is inert and says why.

15 shell tests, axe clean. Several assert absence rather than presence: no
quota meter, no demo-state switch, no nav link to person detail before one is
open. The use-constraint wording is asserted clause by clause, because it is
the product's stated position and not decoration.

Two things this session deliberately did **not** do. `.btn` was left alone —
the old pages are now inside `.app-shell`, and restyling a shared class would
have silently restyled four pages S2 was not touching; the Modernist button
system arrives with S3. And `window.matchMedia` is now stubbed in the test
setup, because the shell always renders the theme toggle and jsdom implements
no `matchMedia` — without it every future shell test throws before asserting.

## Redesign S1 — a second palette, and a test that keeps it honest

First unit of the frontend redesign (`design/REDESIGN_PLAN.md`). The Modernist
token layer from the design handoff now exists for **both** themes, and nothing
on screen has moved yet — the tokens are scoped to `.app-shell`, a class no
component carries until S2.

Keeping dark mode is a departure from the handoff, which specifies one light
palette and verifies its four classification bands by hand. That hand
verification is the whole problem: rule 8 requires every band to clear 4.5:1
against its paired background, and adding a second theme doubles the pairs
while moving them out of the range anyone checks by eye. A band that slips to
3.8:1 renders fine, passes every other test, and is simply unreadable for some
of the people it describes.

So the dark set was derived rather than picked, and both themes are now
asserted. `frontend/src/test/contrast.test.ts` parses the tokens out of
`styles.css` and fails the build on any pair below its floor — 40 assertions,
verified to go red by mutating a band and watching it catch. It parses the CSS
as text because vitest runs with `css: false`, and because asserting on the
stylesheet catches a bad *token* rather than one bad render.

Three things worth knowing came out of doing it:

**Light-mode Healthy is 4.53:1, not the 4.59:1 the handoff states.** Watch and
At Risk match to 0.01, so the formula agrees and this is a tooling difference.
It passes, but on 0.03 of headroom — a test now names that number so nobody
tidies the green without seeing what they are spending.

**Dark `--rule` is deliberately 1.62:1, not 3:1.** Rules carry all the structure
in a design with no shadows, and the light palette ships them at 1.30:1.
Matching that relationship is the correct bar; forcing 3:1 makes dark-mode
rules visibly heavier than the design intends.

**Archivo is not loaded, and the handoff's instruction to `@import` it from
Google Fonts cannot be followed.** `src/security/middleware.py` sets
`default-src 'self'` and declares no `font-src`, so both the stylesheet and the
font files would be blocked in production — and third-party fonts would leak
every viewer's IP, a poor trade for a tool that reads employee telemetry. The
tokens fall back to the system UI stack until the woff2 files are self-hosted.

## Validated configuration — the process refuses to start on a bad value

The environment is untyped input from outside the process, which is the one
boundary this codebase was not checking. Every setting was an
`os.environ.get(NAME, default)` somewhere, so a typo and an unset variable were
indistinguishable: the process started on the default and looked healthy.

Two failures came out of that, and both were real.

**A malformed `API_KEYS` was absorbed.** The key ring loaded nothing, generated
a temporary admin key, printed it into a log nobody was watching, and then
rejected every caller — an outage that presents as a client problem.

**The test suite's own isolation was not running.** `tests/unit/conftest.py`
redirects `FEEDBACK_DB_PATH`, `INTERVENTION_DB_PATH` and `MODEL_REGISTRY_DIR` at
`tmp_path` so a test run cannot touch the developer's real data. It had no
effect: the stores captured those paths into module constants at *import* time,
which happens before any fixture runs. The docstring described a protection that
had never once executed. Paths resolve per call now, a probe confirms it, and
the hash-chained access trail (`AUDIT_DB_PATH`) was added to the same fixture.

- **`src/config.py`** — one Pydantic model for every variable this application
  reads. `app.py` builds it before assembling anything, and does not catch
  `ConfigError`: uvicorn exits non-zero and the release does not roll forward.
- **Every problem is reported together**, not the first one. A deployment fixed
  one variable per restart is a deployment nobody finishes fixing.
- **The rules catch the mistakes that are silent**: `*` in `ALLOW_ORIGINS`
  (credentialed CORS, so a wildcard hands any origin an authenticated session),
  the API *key* pasted where its SHA-256 belongs, a salt or webhook secret too
  short to be one, an empty `FOO=$BAR` path override.
- Errors are reported in terms of the variable people set — `ALLOW_ORIGINS`,
  not `allow_origins.0`.
- `src/app_utils/settings.py:get_settings` is now `get_persisted_settings`. Two
  functions of that name in one codebase is a bug waiting for whoever imports
  the wrong one.
- No new dependency: `pydantic-settings` cannot be installed here, and the
  field definitions transfer to it unchanged if that ever stops being true.

## Response models — the generated client now covers responses too

The frontend's types were generated from the backend for paths, methods and
request bodies only. Every handler was annotated `-> dict`, so the schema
described each response as an open object and the response shapes lived in a
hand-written `frontend/src/api/types.ts`.

They had already drifted, and the drift was invisible. `HistoryEvent.event_type`
was a field no handler has ever returned — the event log writes `action` — so the
History page rendered an em-dash in the Type column of every row. The unit test
mocked the same wrong field and passed. An em-dash is what an empty cell is
supposed to look like, so nothing appeared broken.

- **`src/api/schemas/`** — a `response_model` for all 29 JSON routes, split into
  `people` (read off disk, so closed sets are coerced rather than rejected: one
  bad memory file must not blank the cohort view) and `operations` (produced in
  this process, so strict). The three report routes stream files and declare a
  media type instead.
- **`types.ts` now defines nothing.** Every name is an alias onto the generated
  schema, anchored to the route it comes back from.
- **CI fails if `schema.ts` is stale.** It is a committed file that is generated,
  which rots silently; the `check` job regenerates it from the exported schema
  and diffs.
- **Test fixtures are typed** against those responses. An untyped mock is free to
  describe a response the API does not send, which is how the original bug
  survived — and there is now an assertion that the event type actually renders.
- **Closed sets reach the schema**: `verdict` is the `FeedbackVerdict` enum rather
  than a regex, so the frontend's three verdict buttons are checked against the
  backend's three verdicts.
- **`score_range` is absent rather than `[]`** when there is no range. An empty
  array is truthy in JavaScript, so the UI had been offering "a plausible range"
  with no numbers in it.

## Phase 6 (complete) — frontend rebuild

- **All four pages migrated** in §9's order: Diagnostic Room, Console, History,
  Home. React 18 + TypeScript strict + Vite + TanStack Query + React Router.
- **The legacy `static/index.html` is retired.** 2,499 lines that had been
  non-functional since Phase 4 — it sent no API key, so every request it made
  returned 401. Rollback is git (`1d3ff75` and every commit since).
- **CSP no longer allows inline script.** The old file carried ~2,000 lines of
  inline JavaScript, which is what forced `unsafe-inline`; the Vite build emits
  external files. `style-src` still allows inline because React sets element
  styles directly — injected CSS is a far narrower problem than injected script.
- **Playwright E2E against the composed stack** — the FastAPI server serving the
  *built* bundle with the security middleware in place, not the dev server. That
  distinction caught a real bug (below). Wired into CI as its own job.
- **Types generated from the OpenAPI schema.** `scripts/export_openapi.py` →
  `npm run generate:api` → `schema.ts`. Paths, methods and request bodies are
  checked against the backend here; responses followed later (above).
- 23 vitest tests including `jest-axe` on every page, plus 9 Playwright specs.

### What the interface refuses to do
- The registry is alphabetical and **has no sort control** — a test asserts no
  column header is a button. Sorting people by risk is the feature that turns a
  wellbeing tool into a leaderboard.
- At low confidence **the score is not rendered at all**, on every surface. "7/10"
  in large type with a small grey caveat communicates only the first.
- Home reports a *count* of flagged people, never a list of names.
- The clearable event log is visibly separated from the access audit trail,
  which nothing in the UI can touch.
- Destructive actions ask first.

### Two bugs found by running it
- **Deep links and refreshes returned 401.** The SPA uses history routing, so
  `/console` is not a file; it fell through to the security middleware, and a
  document request carries no Authorization header. Fixed with a shell fallback
  plus a test that fails if a data route ever appears outside `/api`.
- **The rate limit broke normal use.** One 30/min bucket for everything: the
  dashboard makes 3–4 calls per page and polls run progress, so a single
  operator tripped a 429. Found because a *different* E2E test failed on each
  run. Reads now have their own 300/min budget; the tight 6/min limit that
  protects the API quota is unchanged.

## CI green, and a reproducible demo cohort

### The CI gates I added had never actually run
`gitleaks` failed on the first push that exercised it — correctly. The E2E job
carried a 64-hex `key_sha256` literal; it was the SHA-256 of a deliberately
public throwaway whose plaintext sat in the comment above it, but no scanner can
tell that from a real token, and neither can a human skimming a diff. The hash is
now derived at runtime, so no literal exists in the repo.

Because `check` had always failed first, the **E2E job had never run at all**.
Its first real run found two tests passing for the wrong reason:

- The "refuses to be a leaderboard" test asserted on a table caption and on
  there being no sortable headers — both vacuous against an empty registry,
  because there is no table. A fresh checkout has no cohort; my machine did.
- One test built its own `browser.newContext()` (which does not inherit
  `baseURL`) and closed it by hand, racing in-flight requests. It failed at
  `context.close()` — the least informative place a test can fail.

And the readiness poll (`curl … && break`) exited 0 whether or not the server
came up, so a dead server produced a **green** step and nine unreadable failures
downstream. A readiness check that cannot fail is not a readiness check.

All three CI jobs — `check`, `web`, `e2e` — now pass.

### The demo generator is reproducible
§5 requires "same seed → byte-identical output" and the generator was unseeded.
`data/weekly/*.csv` are tracked and it overwrites them, so every `mock-data` call
— including the one the E2E suite makes to seed itself — produced a diff of
meaningless number churn. A repository that reports changes nobody made trains
people to discard changes without reading them. Now seeded, with an optional
`seed` in the request body for variety.

## Fixes — a dead root agent, dead code, and a leaky test suite

### The ADK root agent could not run at all
`run_orchestrator` was registered directly as a tool, and its
`progress_cb: Callable | None` parameter has no JSON Schema representation. ADK
builds a schema for every tool before the agent starts, so this raised
`PydanticInvalidForJsonSchema` and took down **every ADK entrypoint together** —
`adk run`, the A2A path, the reasoning-engine adapter.

Invisible to the unit suite, because nothing in it built a tool declaration. The
integration tests caught it, and they are excluded from CI because they need a
live LLM. Fixed with a thin `run_pipeline` wrapper, plus
`tests/unit/test_agent_tools.py` — which builds the declaration, needs no
network, and is the cheap check the expensive suite was the only thing covering.

### The cohort correction was tested code that nothing called
Built and property-tested in Phase 2, reachable from no production path for two
phases: the pipeline scored people one at a time, so a cohort-wide number had
nowhere to come from. `src/domain/cohort_pass.py` computes shifts once for the
whole cohort before anybody is scored, and the orchestrator now passes them to
the detector. Tested code no production path reaches is not a feature, it is a
claim.

### Unit tests could reach a live provider
§6.3 was being honoured by each test remembering to stub its own seam — the same
discipline that produced B1. It had already failed twice: the security suite
spawned real pipeline threads after a refactor moved the name it patched, and a
cohort test hit Gemini the moment its fixture confirmed a signal. Neither was
visible beyond a slow run and some async warnings. `tests/unit/conftest.py` now
blocks every provider seam by default and redirects the stateful stores to
`tmp_path`.

### Also
- **Idempotency now covers all six ingest paths.** DB, object store and
  natural-language were still able to duplicate a week on retry.
- `ingest.py` went past the 400-line limit as a result, so it split into
  `ingest.py`, `ingest_sources.py` and `_ingest_shared.py` — the structure gate
  did its job and the limit was not raised.
- Vitest was picking up the Playwright spec and reporting a failure unrelated to
  the code under test. The two runners are now separated; a red suite that is
  routinely wrong teaches people to ignore it.
- Frontend types are regenerated from the live OpenAPI schema.

## Phase 5 (complete) — API restructure

- **Blocker B4 closed.** `app.py` went from ~1,250 lines and 30+ inline routes to
  a **155-line composition root**: build the app, install middleware and error
  handlers, mount routers, serve static. Nothing else.
- Eight routers under `src/api/routers/` — system, pipeline, employees, reports,
  maintenance, ingest, simulator, evolution. Every handler is thin.
- `src/api/paths.py` holds the directory constants both the routers and the
  composition root need, so neither has to import the other.
- **Fixed a security regression I introduced last commit.** Mounting routers at
  `/api/v1` silently downgraded `GET /api/v1/models` from ADMIN to VIEWER — the
  policy patterns just stopped matching and the route fell through to the
  safe-method default. That is the B1 failure shape in miniature: nothing
  decided the route should be less protected, a path stopped matching a list.
  `canonical_path()` normalises the version segment, and a test checks every
  route under every prefix.
- **All refusals are now RFC 9457.** Middleware runs before the exception
  handlers, so 401/403/413/429 were the only responses still returning plain
  `{"detail": ...}` — meaning the errors a caller meets most often were the only
  ones with a different shape, and the frontend client fell back to a generic
  message on every auth failure.
- **Fixed: the security suite had stopped being hermetic.** Its fixture patched
  `app.run_orchestrator`, which the restructure moved; with `raising=False` that
  silently did nothing and the rate-limit test spawned real pipeline threads
  against real data. Now patched where it is used, with every writable directory
  redirected to `tmp_path`.
- Duplication removed: the main and realtime employee handlers were two
  near-identical 60-line copies; they are one function parameterised by
  directory. A divergence would have meant two tabs of the same dashboard
  disagreeing about the same person.
- `src/domain/signals.py` split — the superseded threshold method moved to
  `threshold_signals.py`, so the module that is actually called holds only the
  method in use.
- `tests/unit/test_structure.py` enforces the exit criterion: no file over 400
  lines, `app.py` has no route handlers, every router is mounted. Two legacy
  files remain over the limit on an explicit exception list **that can only
  shrink** — a test fails if either grows.

## Intervention outcomes + Phase 6 (partial)

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
