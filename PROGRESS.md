# PROGRESS

Read this first, update it last. Current state only — history lives in `CHANGELOG.md`.

**Current phase: Phases 0–6 all complete.** The required track of
`PRODUCTION_EVOLUTION_PROMPT.md` §9 is done. What remains is the optional track
(O1–O4) and the gaps listed below.

Everything committed is green: `ruff`, `ruff format`, `ty`, **397 unit tests**, the
`domain` dependency contract, the `domain` coverage gate (**99.37%**, against a
95% floor), the agent eval suite (9 accuracy + 6 safety, blocking), the frontend's
`tsc --noEmit` strict + **23 vitest tests** with `jest-axe` on every page, and
**9 Playwright E2E specs** against the composed stack. Clean tree.

---

## Phase 5 — API restructure (complete)

**Blocker B4 is closed.** `app.py` is a **155-line composition root**; all 33
routes live in eight routers under `src/api/routers/`. RFC 9457 problem+json on
every error including the middleware refusals, `/api/v1` versioning with the bare
`/api` kept as a hidden alias, and `scripts/export_openapi.py` so the frontend
types cannot drift from what is served.

`tests/unit/test_structure.py` keeps it that way: no file over 400 lines,
`app.py` has no route handlers, every router is mounted. Three legacy files are
on an explicit exception list **that can only shrink** — a test fails if any of
them grows.

Two bugs found while doing it, both mine from the previous commit:
- **`/api/v1` silently downgraded permissions.** `GET /api/v1/models` fell from
  ADMIN to VIEWER because the policy patterns stopped matching. That is the B1
  failure shape exactly — nothing decided the route should be less protected, a
  path stopped matching a list.
- **The security suite had stopped being hermetic.** Its fixture patched
  `app.run_orchestrator` with `raising=False`; the restructure moved that name,
  the patch silently did nothing, and the rate-limit test was spawning real
  pipeline threads against real data.

## Phase 6 — frontend rebuild (complete)

All four pages migrated in §9's order. `static/index.html` retired — 2,499 lines
that had been non-functional since Phase 4 anyway, since it sent no API key.
Retiring it is what let the CSP drop `unsafe-inline` from `script-src`.

Run it with:

```bash
npm --prefix frontend run build
```

then start the server; or `npm --prefix frontend run dev` for hot reload against
a proxied backend. `frontend/dist` is gitignored, so a fresh clone shows a
"build the interface" message until that runs.

**Two bugs the E2E suite found, both invisible to unit tests:**
- **Deep links returned 401.** History routing means `/console` is not a file, so
  it fell through to the security middleware and a document request carries no
  Authorization header. Every refresh was broken.
- **The rate limit broke normal use.** One 30/min bucket for everything; the
  dashboard makes 3–4 calls per page and polls run progress. A *different* E2E
  test failed on each run until the cause was traced here rather than dismissed
  as flake. Reads now have their own budget; the 6/min limit protecting the API
  quota is unchanged.

## New: intervention outcomes

Records what KIND of action a manager took and measures what followed in that
person's own metrics, **correcting for regression to the mean** — without that
correction the tool would report success for interventions that did nothing,
because it flags people at their worst and they revert regardless.

Two structural refusals, both test-guarded:
- **No per-manager scoring.** It would make this a performance tool whose KPI is
  other people's wellbeing metrics.
- **No free text.** Analysing what a manager *said* needs the contents of a
  private 1-on-1. Reasoning is at the top of `src/domain/intervention.py`.

---

## Phase 4 — security baseline (complete)

**Blocker B1 is closed.** Every route requires authentication, enforced by
default-deny middleware in `src/security/` rather than per-route decorators. B1
existed because `POST /api/memory/clear` wiped everything unauthenticated — not
because anyone decided it should be open, but because nothing forced the question
to be asked. `tests/unit/test_security.py` derives the mutating-route list from
the live application, so a route added next month is covered without anyone
remembering.

| Control | Where |
|---|---|
| API keys, roles, HMAC webhook signatures | `src/security/identity.py` |
| Default-deny route policy | `src/security/policy.py` |
| Rate limits, body caps, idempotency | `src/security/limits.py` |
| One authorisation point + security headers | `src/security/middleware.py` |
| Hash-chained audit log | `src/governance/audit.py` |

**There is no "auth off" switch.** With no `API_KEYS` configured the server
generates one ephemeral admin key and prints it loudly at startup. A bypass flag
for local convenience is exactly the flag that ends up set in a deployment.

### Consequence, now resolved for the new UI
The old `static/index.html` sends no key and still gets 401s. The new
`frontend/` SPA handles keys and works — see the Phase 6 section above. The old
file is served alongside during the page-by-page migration and is retired at the
end of it.

---

## Phase 3 — agent evolution (complete)

The system can now find out whether it is right. Until this phase it produced
judgements about people and never once learned whether any were correct.

- **Manager feedback** (`domain/feedback.py`, `evolution/feedback_store.py`,
  `POST /api/feedback`). `harmful` is a separate axis from `not_accurate`: a
  briefing can be accurate and still have damaged someone. **No free-text field
  and no column for one** — a notes box on a form about an employee is where
  health details end up.
- **Model registry** with an asymmetric promotion gate (`evolution/registry.py`):
  never promote unevaluated, never on a thin held-out set, and **any** increase
  in harm blocks promotion however much precision improved. Automatic rollback.
- **Compounding memory** (`domain/continuity.py`): week 8 carries week 3's
  finding, the manager's verdict on it, and whether things improved since.
- **Self-critique** (`domain/critique.py`) before the deny-list validator.
  Catches what a word list structurally cannot: a verdict on someone's inner
  state, a fabricated signal, a missing low-confidence caveat, a surname leak.
- **Calibration** (`evolution/calibration.py`, `GET /api/calibration`): lifetime
  vs recent, and an explicit "not enough feedback to tell".
- **Eval suite blocking in CI** (`scripts/agent_eval.py`).

---

## Phases 0–2 (complete)

- **Phase 0** — green CI, governance enforced at ingest, prohibited fields purged
  everywhere, CLI bypass closed, pushed to
  `github.com/Athish2002/quiet-quitting-detector`.
- **Phase 1** — pure `src/domain/`, agent Protocols + deterministic fakes, the
  entrypoint parity proof (blocker B6), property tests, dependency contract and
  coverage gate.
- **Phase 2** — distributional baselines, CUSUM change-point detection, cohort
  confound removal, first-class uncertainty, per-metric attribution. Evidence in
  `docs/PHASE2_BEFORE_AFTER.md`.

---

## LLM usage — unchanged in intent

Gemini is still the **primary risk classifier**. `compute_risk_index()` is used
by `FakeRiskScorer` and by the eval suite but still has **zero production call
sites**. Demoting the LLM to narrative-only is still pending and must be a
deliberate, announced change — not slipped into a restructure.

## Still simulated / not enforced

Full list in `docs/LIMITATIONS.md`. The ones that matter:

1. **The old `static/index.html` still sends no key** and gets 401s. The new
   `frontend/` SPA works; the old file goes when the migration finishes.
2. `key_by_surrogate=False` by default — pseudonymization exists but is off.
   Must flip to `True`, with `IDENTITY_SALT` set, before real data.
3. **Rate limiting is in-process** — multi-worker deployments multiply the
   effective limit by the worker count. Redis fixes it; that is O1.
4. **Idempotency covers raw paste, upload and webhook.** DB and S3 ingest can
   still duplicate a week on retry.
5. **Cohort correction is not wired into either entrypoint.** It works and is
   tested; wiring it needs a cohort-wide pass before per-employee scoring, which
   the pipeline router can now host.
6. **CSP allows `unsafe-inline`** because the old UI is one HTML file with
   inline scripts. Tightened once that file is retired.
7. Deferred from §7 on purpose: subject-access export route, delete-by-employee,
   scheduled retention purge, key rotation.
8. DB and cloud-bucket ingestion read real storage but are seeded synthetically.

## Decisions made

- **API keys, not OIDC** (Phase 4). OIDC needs an IdP, a redirect flow, session
  handling and a frontend that does not exist until Phase 6; half an OIDC
  integration protects nothing. `Principal` is the seam — an OIDC exchange later
  produces the same object from a token instead of a header.
- **Default-deny everywhere.** Route authorisation, the data allowlist, and the
  domain import contract all work the same way, for the same reason: the thing
  somebody forgets to add to a list is the thing that causes the incident.
- **No new dependencies for the quality gates.** `hypothesis`, `pytest-cov` and
  `import-linter` cannot be installed here (no package-index access), so each is
  implemented on the standard library. A gate that cannot be installed is a gate
  that never runs.
- **`score_range` is not called a confidence interval.** It is a heuristic band
  with no coverage guarantee; saying otherwise would borrow authority the method
  has not earned.
- **Harm is never netted off against accuracy.** A model that finds more true
  positives by writing briefings that hurt people more often has not improved at
  this job.
- **Licence stays MIT.** A use-restricting licence is not OSI-approved, so most
  legal teams auto-block it. The real controls are the runtime purpose binding
  and the allowlist; the README says plainly that a fork can strip them.

## Outstanding (asked for, not yet done)

- **GitHub Pages static showcase** — approved but not built.
- **Branch protection** — verify `check` is listed under "Require status checks".
- **Nothing since Phase 0 has been pushed.** Four phases sit on local `main`.

## Next session

The required track is finished. In rough order of value:

1. **Push.** Nothing has gone to GitHub since Phase 0 — eight commits sit on
   local `main`.
2. **`response_model=` on the handlers.** The generated types cover paths,
   methods and request bodies but not response fields, because handlers return
   bare `dict`. This is the last piece of "a backend change that breaks the
   frontend must fail `tsc`".
3. **Wire the cohort correction into the pipeline.** It works and is tested but
   is not called; it needs a cohort-wide pass before per-employee scoring, which
   the pipeline router is now the right place for.
4. **Split the three oversized legacy files** on the `test_structure.py`
   exception list.
5. **Optional track**: O1 Postgres, O2 observability, O3 a verified deployment,
   O4 load test and runbook.

Note on the environment: PyPI is reachable but `uv` is firewall-blocked from
binding a socket and the venv has no `pip`, so **Python dependencies still cannot
be installed** — the stdlib quality gates stay. **npm works**, which is why the
frontend was feasible.
