# PROGRESS

Read this first, update it last. Current state only — history lives in `CHANGELOG.md`.

**Current phase: Phases 0–4 complete. Phases 5 and 6 are PARTIAL — neither exit
criterion is met. Read the two sections below before assuming otherwise.**

Everything committed is green: `ruff`, `ruff format`, `ty`, **386 unit tests**, the
`domain` dependency contract, the `domain` coverage gate (**99.36%**, 1251/1259,
against a 95% floor), the agent eval suite (9 accuracy + 6 safety, blocking), and
the frontend's `tsc --noEmit` + 9 vitest tests including a `jest-axe` check.
Clean tree.

---

## Phase 5 — API restructure (PARTIAL, exit criterion NOT met)

Done: RFC 9457 problem+json errors app-wide (`src/api/errors.py`), `/api/v1`
versioning, `scripts/export_openapi.py`, and the first extracted router
(`src/api/routers/evolution.py`).

**Not done: `app.py` is still ~1,250 lines with roughly 28 routes in it.** The
criterion is "no file over 400 lines; `app.py` is composition root only". The
remaining routes need moving into routers by resource — mechanical, but a
session's work on its own.

## Phase 6 — frontend (PARTIAL, one page of four)

`frontend/` is React 18 + TS strict + Vite + TanStack Query + Router, installed
and passing. **The Diagnostic Room is migrated; Console, History and Home are
placeholders that say so.** §9 prescribes exactly this pace — "migrate page by
page, one page per session, running alongside `static/index.html` until parity is
proven".

**The UI works again.** Phase 4 left it receiving 401s; `ApiKeyGate` now prompts
for a key, and a 401 clears the stored key and re-prompts rather than hanging.
Verified end to end against the running backend.

Still to do: the other three pages, the generated API client as source of truth
(`npm run generate:api` exists but types are hand-written), Playwright E2E.

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
4. **Idempotency covers webhook ingest only.** Upload, raw paste, DB and S3 can
   still duplicate a week on retry.
5. **Cohort correction is not wired into either entrypoint.** It works and is
   tested, but computing shifts needs a pass over all employees before scoring
   any of them — still blocked on finishing the Phase 5 restructure.
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

**Finish Phase 5.** Move the remaining ~28 routes out of `app.py` into
`src/api/routers/` by resource: health/metrics, pipeline, employees, reports,
memory, ingest, scoring. Thin handlers only.
*Exit: no file over 400 lines; `app.py` is composition root only.*

Fold in while restructuring, both currently blocked on it:
- the **cohort correction** (needs a cohort-wide pass before per-employee scoring)
- **idempotency** on the ingest routes other than the webhook

**Then Phase 6, one page per session**: Console → History → Home, then retire
`static/index.html` and add Playwright.

Note on the environment: PyPI is reachable but `uv` is firewall-blocked from
binding a socket and the venv has no `pip`, so **Python dependencies still cannot
be installed** — the stdlib quality gates stay. **npm works**, which is why the
frontend was feasible.
