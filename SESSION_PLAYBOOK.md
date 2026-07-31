# Session Playbook — Getting Maximum Work per Unit of Budget

You have a weekly Claude Code limit. Most budget on a codebase this size is burned on **re-reading
files** and **sprawling, unreviewable changes**, not on writing code. This playbook exists to stop
both.

---

## The five rules that actually save budget

**1. Name the files. Every time.**
An unscoped instruction makes Claude search the repo to orient itself, which can cost more than
the edit. Compare:

- ✗ "Add auth to the API" → greps the whole tree, reads `app.py` twice
- ✓ "Add auth. Read `app.py` lines 1-130 and `src/app_utils/settings.py` only. Do not read
  `static/index.html`."

**2. `/clear` between tasks, never between steps of one task.**
Context carries the files already read — clearing mid-task makes it re-read them. Clearing between
tasks stops an hour of irrelevant history riding along in every subsequent request.

**3. `PROGRESS.md` is the handoff, not the conversation.**
Each session ends by writing what shipped, what's next, and any decision made. The next session
starts by reading that one file instead of re-deriving state from the codebase. This is the single
highest-leverage habit here.

**4. Plan mode for anything large; straight to work for anything small.**
For a big phase: `"Plan only, no edits. Max 10 bullets."` Review it, then approve. A bad plan
caught in 10 bullets costs a fraction of a bad implementation caught in 600 lines.
For a small fix: skip planning entirely, it's pure overhead.

**5. Do not spawn subagents.**
Each one starts cold and re-reads the repo from scratch. On this plan they are the expensive path.
Let the main session do the work.

---

## Session shape

```
1. /clear
2. Paste the session prompt (below)
3. Review the plan if one was requested — reject early, cheaply
4. Let it work to green (it runs lint/types/tests itself)
5. "Update PROGRESS.md and CHANGELOG.md, then commit."
```

**Stop when the exit criterion is met, even if budget remains.** Starting the next phase with 15
minutes left is how you get a half-migrated repo.

---

## Copy-paste session prompts

Prefixed assumption: `CLAUDE.md` auto-loads, so the spec and rules are already in context. Do not
re-paste them.

### Session 1 — Assessment + Phase 0 (small)
```
Read PROGRESS.md if it exists, otherwise §3 of PRODUCTION_EVOLUTION_PROMPT.md.

First: confirm, correct, or extend the 12 blockers in §3 with evidence. Report in
under 20 lines. Do not write code yet.

Then, on my go-ahead, do Phase 0:
- review the uncommitted working tree, split it into coherent commits
- add .github/workflows/ci.yml running ruff, ty, and pytest
- pin dependencies
Exit: green CI, clean git status.
```

### Session 2 — Phase 1, part A: domain extraction (medium)
```
Phase 1, part A. Read src/risk_scorer_agent.py and src/trend_detector_agent.py only.

Extract the pure scoring logic — baselining, signal confirmation, risk index,
healthy-streak decay — into src/domain/ with Pydantic models. No I/O, no LLM
calls, no framework imports in that package.

Plan only, max 10 bullets. No edits until I approve.
```

### Session 3 — Phase 1, part B: wire up + prove parity (medium)
```
Phase 1, part B. Make app.py and run_pipeline.py both call src/domain/ instead of
their own copies of the logic. Read only the functions you are replacing.

Then write property tests (Hypothesis): worse metrics never lower risk, score
stays in [1,10], re-running a week is idempotent, decay behaves per spec.

Exit: >=95% coverage on src/domain/, and both entrypoints produce byte-identical
output on data/weekly/*.csv. Prove the last one by running both and diffing.
```

### Sessions 4-6 — Phase 2: honest statistics (large, split across sessions)
```
Phase 2 of PRODUCTION_EVOLUTION_PROMPT.md, §6.1. This session: <ONE of>
  (a) distributional personal baselines (median/MAD) replacing point thresholds
  (b) change-point detection to separate regime shift from a single bad week
  (c) uncertainty: confidence intervals + an explicit insufficient_data state
  (d) per-metric attribution so a briefing can say why

Work in src/domain/ only. Property tests alongside. Then show me a before/after
on data/weekly/*.csv: which previously-flagged signals the new method rejects as
noise, and why that is the correct call.
```

### Sessions 7-9 — Phase 3: evolution (large, split across sessions)
```
Phase 3 of PRODUCTION_EVOLUTION_PROMPT.md, §6.2. This session: <ONE of>
  (a) manager feedback capture (accurate / not accurate / harmful + reason), stored
  (b) versioned model registry: retrain -> held-out eval -> promote -> auto-rollback,
      with every prediction recording its model version
  (c) compounding memory: week 8 references the week 3 intervention and its outcome
  (d) self-critique pass before the punitive-language validator
  (e) calibration tracking + eval-gating prompt changes in CI

CI must never call a real LLM — put agents behind Protocols with a deterministic fake.
```

### Session 10 — Phase 4: security baseline (medium)
```
Phase 4. Read app.py's route definitions and src/app_utils/settings.py only.

Add: auth on every mutating route (401 for unauthenticated), roles viewer/manager/
admin, rate limiting, idempotency keys on ingest, security headers, gitleaks in CI.
/api/memory/clear, /api/history/clear and /api/mock-data are admin-only and audited
with actor identity.

Write the security test suite first, then make it pass.
```

### Session 11 — Phase 5: API restructure (medium)
```
Phase 5. Split app.py into routers by resource under apps/api/routers/. Handlers stay
thin and delegate to services. Version everything under /api/v1. RFC 9457 problem+json
error envelope.

Exit: no file over 400 lines, app.py is composition root only, all existing tests pass
unchanged except for the /api/v1 path prefix.
```

### Sessions 12+ — Phase 6: frontend, one page per session (large)
```
Phase 6, page <N> of 4: <Diagnostic Room | Console | History | Home>.

Scaffold apps/web (Vite + React + TS strict + Tailwind + TanStack Query) if it does
not exist. Generate the API client from the backend OpenAPI schema — do not hand-write
types.

Port ONLY this page. Read just the corresponding section of static/index.html; do not
read the whole file. Keep the old page serving until parity is proven.

Include: Vitest tests, jest-axe check, sanitized markdown rendering (no raw
dangerouslySetInnerHTML of model output).
```

### Any session — closing prompt
```
Update PROGRESS.md (shipped / next / decisions made / anything still simulated) and
CHANGELOG.md. Then commit with a message explaining why, not what.
```

---

## Sequencing note

Phases 2 and 3 are the ones a reviewer will find genuinely impressive, and they depend on Phase 1.
Phase 6 (frontend) is the single largest consumer of budget and delivers the least novel signal —
if the weekly limit bites, ship the Diagnostic Room page only, leave the rest on the old HTML, and
note it honestly in `docs/LIMITATIONS.md`. A rigorous half-migrated frontend with a clear rationale
reads better than a rushed complete one.
