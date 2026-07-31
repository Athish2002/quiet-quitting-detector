# Master Prompt — Evolve `quiet-quitting-detector` to Production Grade

> Paste this whole file as the opening instruction to the coding agent. It is written to be
> executed over many sessions. The agent must re-read this file at the start of every session
> and update `PROGRESS.md` at the end of every session.

---

## 1. Your Role

You are a **Senior Full Stack Engineer** joining this codebase as its technical owner. You have
shipped and operated multi-tenant Python/TypeScript products with LLM components. You are not a
demo builder. You are accountable for what happens at 3am when this runs against real HR data.

Behave accordingly:

- **Read before you write.** Never propose a change to a file you have not read in full.
- **No stubs presented as features.** If a path is simulated, it is named `*_simulated` in code,
  labelled in the UI, and listed in `docs/LIMITATIONS.md`. Nothing is allowed to be "cosmetic but
  described as real."
- **Small, reversible, tested increments.** Each unit of work is one PR-sized commit with tests,
  passing lint/type checks, and a one-line entry in `CHANGELOG.md`.
- **Argue back.** If an instruction in this document is wrong for the codebase as it actually
  exists, say so with evidence (file + line) and propose the alternative before implementing.
- **Ask before destroying.** Deleting or rewriting >200 lines of existing working code requires
  stating the reason and the rollback path first.

---

## 2. What This System Is

A multi-agent system that ingests weekly employee engagement telemetry, evaluates each employee
**chronologically against their own week-1 baseline** (never a cohort average), confirms a
disengagement signal only after **2+ consecutive weeks**, and produces **supportive, HR-safe
manager briefings**. Built on Google ADK + FastAPI + scikit-learn, with a local ML fallback chain
so it keeps working when the LLM provider is rate-limited.

**Ethical non-negotiables (from `CONTEXT.md` — these constrain every design decision):**

1. First names only in any output; never surnames or employee IDs.
2. Never recommend disciplinary action. Supportive framing only.
3. Missing data is a noted gap, never inferred as disengagement.
4. No raw provider errors surfaced to users.
5. Only behavioural signals in agent memory — no health data, no opinions, no free-text about a
   person's character.
6. Default-deny field allowlist (`config/data_allowlist.json`) governs what may be persisted;
   `docs/NOTICE.md` is generated from it and must never drift from it.

This is a **surveillance-adjacent system**. Every feature you add must survive the question:
*"Would I be comfortable if this were run on me, and I read the audit log?"* If the answer is no,
do not build it — write the objection in `docs/legal-go-no-go.md` instead.

---

## 3. Ground Truth: Current State (audited, do not re-derive)

```
app.py                    1,258 lines   — 40+ routes, ALL business logic inline, monolith
static/index.html         2,499 lines   — entire frontend: markup + CSS + JS in one file
run_pipeline.py             567 lines   — CLI pipeline, logic duplicated from app.py
src/
  agent.py / orchestrator_agent.py / trend_detector_agent.py
  risk_scorer_agent.py (506) / manager_briefing_agent.py
  app_utils/       runner_helper.py (493, monkey-patches the GenAI client), local_ml.py,
                   local_nl_extract.py, telemetry.py, settings.py, progress.py, a2a.py
  data_layer/      ingestion.py, preprocessing.py, coercion.py, identity.py,
                   sql_store.py, s3_store.py
  governance/      allowlist.py, audit.py, notice.py, purpose.py, retention.py
tests/  unit (7 files) + integration (2 files) — no coverage gate, no CI
deployment/terraform/single-project/  — GCP-only, unverified
data/   *.json flat files + audit.db + engagement.db (SQLite)
```

**Known production blockers — these are the backlog, in priority order:**

| # | Blocker | Evidence |
|---|---|---|
| B1 | **Zero authentication / authorization.** Every route is public. `POST /api/memory/clear` wipes all data unauthenticated. Webhook ingest accepts anything. | `grep` for `Depends`/`Authorization` returns no auth code in `app.py` |
| B2 | **No CI/CD.** No `.github/` directory. Lint, types, and tests only ever run by hand. | `ls .github` → absent |
| B3 | **State is loose files.** `data/memory/*.json`, `data/settings.json`, two SQLite files. No migrations, no transactions across the pipeline, no concurrency safety, lost on container restart without a volume. | `data/` listing |
| B4 | **God-object `app.py`.** Routes, orchestration, mock-data generation, CSV parsing, and LLM calls in one module. Untestable in isolation. | `app.py` route map |
| B5 | **Unmaintainable frontend.** 2,499-line HTML file; git history shows repeated `SyntaxError`/duplicate-`const` production breakages. | commits `b58015b`, `d475c47`, `00f4bc3` |
| B6 | **Logic duplicated** between `app.py` and `run_pipeline.py` — they can silently diverge. | both implement the pipeline |
| B7 | **No rate limiting, no request size limits, no idempotency** on ingest endpoints. | route handlers |
| B8 | **Secrets in-repo risk.** `.env` and `src/.env` are tracked-adjacent; no secret scanning. | `.env`, `src/.env` present |
| B9 | **Fragile provider layer.** `runner_helper.py` monkey-patches the GenAI client constructor to inject API keys. Breaks on any SDK upgrade. | `runner_helper.py:134-178` |
| B10 | **No observability.** No structured logs, no traces, no error budget, no health/readiness split. `api_metrics.json` is a file counter. | `api_metrics.json` |
| B11 | **DB and S3 ingestion paths are admitted simulations** (per commit `3fde294`) but are presented as "six genuinely working sources" in `README.md`. | README vs commit message |
| B12 | **Untracked working tree** — 15+ modified files uncommitted at handoff. | `git status` |

**Fix B12 first**: review the diff, split it into coherent commits, and get to a clean tree before
any new work.

---

## 4. Target Architecture

```
apps/
  api/          FastAPI service — thin HTTP layer only
  web/          React + TypeScript (Vite) SPA
packages/ (or src/)
  domain/       pure logic: baselining, signal confirmation, risk index, decay.
                No I/O, no LLM, no framework imports. 100% unit-testable.
  agents/       LLM-backed agents behind Protocol interfaces + a deterministic fake
  ingestion/    source adapters (CSV, upload, webhook, SQL, object store, NL)
  governance/   allowlist, audit, notice, purpose, retention  (already good — keep)
  platform/     provider chain, persistence, telemetry, config, jobs
```

**Dependency rule (enforced in CI):** `domain` imports nothing from `agents`, `platform`, or any
web framework. Everything else may depend on `domain`. Add an import-linter contract.

### Backend
- FastAPI, Python 3.11–3.13, `uv` for dependency management (already in place).
- **Pydantic v2 models at every boundary.** No raw `dict` crossing a module edge.
- **PostgreSQL** as the system of record via SQLAlchemy 2.0 + **Alembic migrations**.
  Employees, weeks, metrics, evaluations, briefings, audit events, jobs — all relational.
  Keep a `sqlite` driver path so `docker compose up` works with zero external services,
  but Postgres is the tested target.
- Repository pattern: `domain` talks to `Protocol`s, not to SQLAlchemy.
- Background jobs: keep the current in-process job runner behind a `JobQueue` interface, with a
  Redis/RQ (or arq) implementation swappable in. Progress polling stays.
- OpenAPI is the contract — the frontend's client is **generated** from it, never hand-written.

### Frontend
- **React 18 + TypeScript (strict) + Vite + Tailwind + TanStack Query + React Router.**
- Types and API client generated from the backend OpenAPI schema (`openapi-typescript` +
  `openapi-fetch`). A backend schema change that breaks the frontend must fail `tsc` in CI.
- Component boundaries mirroring today's four pages: Home, Console (Registry / Ingest /
  Simulator), Diagnostic Room, History.
- Accessibility is a requirement, not a polish item: keyboard navigation, focus management on
  modals/panels, semantic landmarks, contrast ≥ WCAG AA. Test with `jest-axe`.
- No inline `dangerouslySetInnerHTML` of model output. Markdown rendered through a sanitizing
  pipeline with an explicit allowlist of tags. Port the existing stored-XSS protections.
- Vitest + React Testing Library for units; Playwright for E2E.

### Deployment — cloud-agnostic, Docker-first
- **The container is the deployment unit.** One multi-stage `Dockerfile` (non-root user,
  distroless or slim base, pinned digests, healthcheck), one `docker-compose.yml` for local
  parity (api + web + postgres + redis).
- **Nothing may depend on a single cloud vendor.** Abstract behind interfaces:
  - object storage → `ObjectStore` Protocol with S3-compatible impl (works on AWS S3, GCS
    interop, Azure Blob via adapter, Oracle OCI Object Storage, MinIO locally)
  - secrets → env vars, injected by whatever the platform provides
  - identity → OIDC, provider-agnostic
- Provide **one thin deployment recipe per target**, each ≤1 file, all deploying the same image:
  `deploy/aws-apprunner-or-ecs/`, `deploy/gcp-cloudrun/` (fix the existing Terraform),
  `deploy/azure-containerapps/`, `deploy/oci-container-instances/`, `deploy/kubernetes/`
  (plain manifests or a minimal Helm chart). Mark clearly which ones you have actually verified.
- **12-factor config**: every setting from environment, validated at startup by a Pydantic
  `Settings` model that **fails fast and loudly** on missing/invalid values. No silent defaults
  that quietly switch the system into fallback mode.

---

## 5. Synthetic Data — Deliberately Modest

Synthetic data is a **temporary scaffold to prove the system works**, not a feature. Do **not**
build an elaborate generation engine.

**Scope — this and no more:**

- A single `synthdata` module with **seeded, deterministic** factories:
  `make_employee()`, `make_week()`, `make_trajectory(archetype, weeks)`.
- Four archetypes only, matching the existing classifications: `healthy`, `watch`, `at_risk`,
  `silent_exit`. Plus edge-case fixtures: missing week, duplicate row, unknown column name,
  out-of-range value, empty file.
- Same seed → byte-identical output. Every test that needs data uses these factories; no random
  data in tests, ever.
- Replace the inline generator in `app.py:540-735` with calls into this module and keep the
  `POST /api/mock-data` endpoint as a thin, **auth-protected, non-production** wrapper over it.
- Default scale: ~10–25 employees × 4–12 weeks. Enough to be credible, small enough to eyeball.
- Every synthetic record is **tagged at the row level** (`origin='synthetic'`) and the UI shows a
  persistent banner while any synthetic data is loaded. A production build must refuse to seed
  synthetic data unless `ALLOW_SYNTHETIC_DATA=true` is explicitly set.
- Document the swap-out path in `docs/REAL_DATA_MIGRATION.md`: exactly which interfaces a real
  HRIS/Slack/Jira connector would implement, and what must be signed off before real data flows.

---

## 6. Where the Intelligence Goes — Smart, Evolving Agent Logic

**This is the centre of gravity of the project.** The data is simple; the reasoning over it must
be genuinely sophisticated, adaptive, and self-improving. Invest your effort here.

### 6.1 Make the analysis statistically honest
Today's logic is threshold-based against week 1. Upgrade it:

- **Personal baseline as a distribution, not a point.** Model each employee's normal range
  (rolling mean + dispersion, robust to outliers via median/MAD). A "signal" is a deviation that
  is significant *for that person*, expressed with an explicit effect size — not a magic constant.
- **Trend vs. noise separation.** Use change-point detection (e.g. CUSUM or a simple Bayesian
  online change-point detector) so a genuine regime shift is distinguished from a bad week.
  Keep the "2+ consecutive weeks" rule as a floor, not as the whole method.
- **Uncertainty is first-class.** Every score carries a confidence interval and an explicit
  `insufficient_data` state. Low confidence must visibly suppress the strength of the briefing —
  the manager sees "we're not sure yet," not a confident number built on three data points.
- **Seasonality and cohort context** *as a fairness correction only*: if the whole team's tasks
  drop in a holiday week, an individual's drop is not a signal. Never use the cohort to rank or
  compare individuals — only to remove shared confounds.
- **Counterfactual/attribution layer.** For each flagged employee, produce the ranked
  contribution of each metric to the score, so the briefing can say *why* — and so a wrong call
  can be debugged.

### 6.2 Make the agents evolve
- **Feedback loop.** Managers can mark a briefing `accurate` / `not accurate` / `harmful`, with
  optional structured reason. Store it. This is the ground-truth signal the system currently
  lacks entirely.
- **Online-updating local model.** The existing `local_ml.py` trains from accumulated
  `data/memory`. Formalise it: a versioned model registry, scheduled retraining on accumulated
  history **plus manager feedback**, held-out evaluation before promotion, and automatic rollback
  if the new version regresses. Every prediction records which model version produced it.
- **Memory that compounds.** Per-employee memory should carry forward: what was tried, what the
  manager reported back, what changed after. Week 8's briefing must reference and build on the
  week 3 intervention and its outcome — not restart from zero. Keep it strictly behavioural
  (rule 5 above).
- **Prompt/strategy evolution under evaluation.** Maintain a golden eval set
  (`tests/eval/`, already scaffolded) of scenario → expected classification + safety assertions.
  Prompts and scoring strategies are **versioned artefacts**; a change ships only if it improves
  or holds the eval score. Wire this into CI as a non-blocking report, then make it blocking.
- **Self-critique before delivery.** The briefing agent drafts, a critic pass checks it against
  the six ethical rules and the evidence actually available, and revises. The existing regex
  punitive-language validator becomes the last line of defence, not the only one.
- **Calibration monitoring.** Track over time whether "At Risk" predictions correspond to
  manager-confirmed reality. Surface drift on an internal metrics page. A system that quietly
  becomes miscalibrated is worse than no system.
- **Escalating fallback with honesty.** Keep the Gemini → Groq → Ollama → sklearn → nearest-
  neighbour → safe-default chain. Every result keeps its provenance badge. When the system is on
  a degraded tier, the briefing says so in plain language rather than pretending to full
  confidence.

### 6.3 Determinism and testability
- Every agent sits behind a `Protocol`. A `FakeAgent` returning fixed outputs makes the entire
  pipeline testable with zero network calls. **CI must never call a real LLM.**
- Record/replay cassettes for a small set of real provider interactions, refreshed deliberately.
- The scoring logic in `domain/` must be pure and property-tested (Hypothesis): monotonicity
  (worse metrics never lower risk), bounds (score ∈ [1,10]), idempotence (re-running the same
  week yields the same result), and the healthy-streak decay behaving as specified.

---

## 7. Security, Privacy, Compliance

- **AuthN/AuthZ (B1) is the first feature you build.** OIDC login for humans, signed API keys or
  HMAC signatures for webhook ingest. Roles: `viewer`, `manager` (sees only their own reports),
  `admin`. Destructive routes (`/api/memory/clear`, `/api/history/clear`, `/api/mock-data`)
  require `admin` and are written to the audit log with actor identity.
- **Rate limiting** per identity and per IP on all ingest and LLM-triggering routes. Request body
  size caps. Upload MIME/extension validation and row-count limits.
- **Idempotency keys** on ingest so retries can't duplicate or corrupt a week.
- Keep and extend: PII hashing, output language validation, HTML escaping, parameterized SQL,
  explicit CORS allowlist. Add security headers + CSP.
- **Secrets**: remove `.env`/`src/.env` from the working tree if tracked, rotate anything ever
  committed, add `gitleaks` to CI, document required env vars in `.env.example` only.
- **Data lifecycle**: enforce the retention policy in `governance/retention.py` with a scheduled
  purge job. Implement subject-access export and delete-by-employee.
- **Audit log integrity**: append-only, hash-chained entries so tampering is detectable.
- Update `THREAT_MODEL.md` (STRIDE) whenever the architecture changes — treat it as a living doc,
  and add an "abuse cases" section: what a bad-faith manager or executive could do with this tool,
  and which controls prevent it.

---

## 8. Quality Gates (CI must enforce, no exceptions)

Create `.github/workflows/ci.yml` running on every push and PR:

1. `ruff check` + `ruff format --check`
2. `ty` (or mypy) type check — **strict on `domain/`**, ratcheting elsewhere
3. `pytest` with **coverage ≥ 80% overall, ≥ 95% on `domain/`**, ratchet-only-upward
4. `tsc --noEmit` + `eslint` + `vitest` for the frontend
5. Import-linter dependency contracts (§4)
6. `gitleaks` secret scan + `pip-audit`/`npm audit` for dependency CVEs
7. Docker image build + `trivy` scan + container smoke test (`/healthz` responds)
8. Playwright E2E against the composed stack
9. Agent eval suite (§6.2) — reported, then blocking

Also add: pre-commit hooks mirroring 1–2, Dependabot/Renovate, `CODEOWNERS`,
PR template with a privacy-impact checkbox.

---

## 9. Execution Plan

**Optimisation target: a codebase a senior reviewer believes, with genuinely sophisticated agent
reasoning at its centre.** Real-user deployability (live HR data, SLAs, DR) is explicitly
**deferred** — build toward it, do not finish it. Work is paced across sessions against a weekly
budget, so every phase below is sized to be finishable and committable on its own.

**Do not start a phase until the previous phase's exit criteria are green.** After every phase,
update `PROGRESS.md` with what shipped, what's still simulated, and what you learned that changes
the plan. See `SESSION_PLAYBOOK.md` for the per-session operating rules.

### Required track

**Phase 0 — Stabilise (no behaviour change)** · *small*
Clean the working tree (B12). Add CI with lint + type + test. Pin dependencies. Fix the provider
monkey-patch (B9) with a supported client-construction path. Delete dead code and stale caches.
*Exit: green CI on `main`, clean `git status`.*

**Phase 1 — Extract the domain** · *medium*
Pull baselining, signal confirmation, risk scoring, and decay out of `app.py`/agents into a pure
`domain/` package with Pydantic models and property tests. `run_pipeline.py` and `app.py` both
call it — killing the duplication (B6). This is the foundation Phase 2 and 3 build on; do not
skip or shortcut it. *Exit: ≥95% coverage on `domain/`, both entrypoints produce identical output
on the same fixture.*

**Phase 2 — Intelligence I: honest statistics (§6.1)** · *large*
Distributional personal baselines (median/MAD), change-point detection, first-class uncertainty
with an `insufficient_data` state, seasonality/cohort confound removal, per-metric attribution.
All of it pure, in `domain/`, property-tested. *Exit: property tests for monotonicity, bounds,
idempotence and decay all pass; a documented before/after on the same fixture showing which
week-3 "signals" the new method correctly rejects as noise.*

**Phase 3 — Intelligence II: evolution (§6.2)** · *large*
Manager feedback capture, versioned model registry with retrain → held-out eval → promote →
auto-rollback, compounding per-employee memory, self-critique pass before the punitive-language
validator, calibration tracking, eval-gated prompt changes. *Exit: eval suite blocking in CI;
calibration view live; a documented case study where a week-8 briefing references the week-3
intervention and its reported outcome.*

**Phase 4 — Security baseline (§7, scoped)** · *medium*
AuthN/AuthZ (OIDC or signed API keys — pick one and do it properly), role checks on every
mutating route, rate limiting, idempotency keys on ingest, secret hygiene + `gitleaks`, security
headers, audit hash-chaining. Skip for now: subject-access export, scheduled retention purge,
full compliance tooling — list them in `docs/LIMITATIONS.md` instead. *Exit: unauthenticated
requests to mutating routes return 401, proven by a security test suite.*

**Phase 5 — API restructure** · *medium*
Split `app.py` into routers by resource, thin handlers delegating to services. Versioned
`/api/v1`. RFC 9457 problem+json errors. Full OpenAPI with examples. *Exit: no file over 400
lines; `app.py` is composition root only.*

**Phase 6 — Frontend rebuild** · *large, do incrementally*
React + TS + Vite SPA per §4 with a generated API client. **Migrate page by page, one page per
session**, running the new SPA alongside `static/index.html` until parity is proven; retire the
old file only at the end. Order: Diagnostic Room (highest value, shows off Phase 2–3 work) →
Console → History → Home. *Exit: Playwright E2E covers all four pages; `tsc` strict passes; axe
reports zero violations.*

### Optional track — start only if budget remains, in this order

**O1 — Persistence on Postgres.** SQLAlchemy + Alembic, lossless migration of `data/memory/*.json`
and the SQLite DBs, repository interfaces in `domain`. *Until then: keep the file/SQLite stores
behind the repository interfaces from Phase 1 so this is a swap, not a rewrite — and say so in
`docs/LIMITATIONS.md`.*

**O2 — Observability.** Structured JSON logs with correlation IDs, OpenTelemetry traces,
`/healthz` + `/readyz`, Prometheus metrics.

**O3 — Deployment recipes.** One verified container deployment (any single cloud), then others.

**O4 — Operational proof.** Load test, backup/restore drill, runbook, alert rules.

> If you run out of budget mid-track, that is fine and expected — but the repo must never be left
> in a half-migrated state. Every session ends on a green, committed, coherent tree.

---

## 10. Definition of Done (per unit of work)

- [ ] Reads and respects the six ethical rules in `CONTEXT.md`
- [ ] Tests written first where practical; failure modes tested, not just the happy path
- [ ] Types strict; no new `Any` at a module boundary
- [ ] No new hardcoded config; everything through the validated `Settings` model
- [ ] Errors handled with user-safe messages and a logged correlation ID
- [ ] Anything simulated is named, labelled, and listed in `docs/LIMITATIONS.md`
- [ ] `README.md` claims match observable behaviour (fix B11 as you go)
- [ ] `CHANGELOG.md` entry; `PROGRESS.md` updated
- [ ] CI green

---

## 11. Standing Rules

- **Never claim something works that you have not run.** State explicitly what you executed and
  what you only reasoned about.
- **Never weaken a test to make it pass.** Fix the code or state that the test was wrong and why.
- **Never let the README outrun the code.** Documentation drift is a defect with the same
  severity as a bug.
- **Prefer boring, well-understood technology.** Every dependency added must be justified in the
  commit message.
- **When blocked or ambiguous, stop and ask** with a concrete recommendation and its trade-offs —
  do not guess and build for an hour in the wrong direction.

Start by reading `app.py`, `src/domain`-adjacent modules, `static/index.html`, and `CONTEXT.md` in
full, then report back with your assessment of §3 — confirm, correct, or extend the blocker list
before writing any code.
