# PROGRESS

Read this first, update it last. Current state only — history lives in `CHANGELOG.md`.

**Current phase: Phase 0 complete. Phase 1 IN PROGRESS (~60%) — do not assume it is done.**

Last session ended early (context budget), mid-Phase-1. Everything committed and
pushed is green: `ruff`, `ruff format`, `ty`, **201 unit tests**, clean tree.

---

## Phase 1 — where it actually stands

### Done
- **`src/domain/` package created** — pure, no I/O, no LLM, no framework imports.
  - `models.py` — Pydantic v2: `WeekMetrics`, `Baseline`, `Signal`, `HistoryRecord`,
    `RiskAssessment`, `Severity`, `Classification`. Every metric is `Optional` so
    missing stays missing.
  - `signals.py` — `find_baseline`, `detect_week_flags`, `confirm_consecutive`,
    `assign_severity`, `confirm_signals`. Lifted from `trend_detector_agent.py`.
  - `risk.py` — bands, `classify`, `compute_recurrence_bonus`, decay,
    `next_healthy_streak`, `clamp_score`. Lifted from `risk_scorer_agent.py`.
- **Both agents rewired** to delegate to `domain/`. Public signatures of
  `detect_trends()` and `score_risk()` unchanged, so `app.py`, `run_pipeline.py`
  and all existing tests were untouched and still pass.
- **`compute_risk_index()` written but deliberately NOT wired in** — see decisions.

### Not done (this is the next session's work)
1. **Property tests (Hypothesis)** on `domain/`: monotonicity (more/severer
   signals never lower the score), bounds (score ∈ [1,10]), idempotence, decay
   clearing the bonus at exactly 4 healthy weeks, the 2+-consecutive-week rule.
2. **Import-linter contract in CI** — `domain` must not import from `agents`,
   `app_utils`, `data_layer`, or any web framework. Without it the boundary erodes.
3. **≥95% coverage on `src/domain/`** — not yet measured at all.
4. **`RiskScorer` / `TrendEnricher` Protocols + a deterministic `FakeScorer`** —
   required by §6.3 and a prerequisite for the parity proof below.
5. **Parity proof** — run both entrypoints against the fake and diff.

---

## Shipped and pushed (Phase 0, complete)

- **Green CI** (`.github/workflows/ci.yml`): ruff, ruff format, `ty`, unit tests,
  installed with `uv sync --frozen`. Integration tests marked
  `@pytest.mark.integration` and excluded (§6.3 — CI must never call a real LLM);
  they fail locally without GCP credentials, which is pre-existing.
- **Governance layer** enforced at ingest: default-deny allowlist, purpose binding
  that refuses punitive uses in code, append-only audit log (DB triggers),
  retention with verified real deletion, notice generated from the allowlist.
- **Prohibited fields removed everywhere**: `sick_days` (health data),
  `sentiment` (emotion inference), `task_accuracy` (performance metric) — gone
  from both entrypoints, stored CSVs, mock generator, simulator/webhook models,
  and the LLM extractor prompt that had been *instructing Gemini to extract them*.
- **CLI governance bypass closed** — `run_pipeline.py` now calls the shared
  `preprocess_employee_records`. `tests/unit/test_entrypoint_parity.py` fails if
  the duplication returns.
- **Identity resolution + pseudonymization**, tolerant value coercion, week
  bounds, atomic pipeline slot, locked/atomic metrics, multi-provider LLM chain.
- **Public repo standards**: README "what this is deliberately not", `SECURITY.md`,
  `CODE_OF_CONDUCT.md`, PR template with privacy checklist, Dependabot.
- **Pushed** to `github.com/Athish2002/quiet-quitting-detector`.

---

## LLM usage — unchanged in intent

Gemini is still the **primary risk classifier**: `score_risk()` asks
`gemini-2.5-flash` for the 1–10 score. Chain is Gemini → Groq → Ollama → local ML
(Groq/Ollama opt-in via env; with neither set, behaviour is identical to the
original Gemini-only chain).

`compute_risk_index()` exists in `domain/risk.py` but has **zero call sites**.
Demoting the LLM to narrative-only is **Phase 6**, and must be a deliberate,
announced change — not slipped into an extraction phase.

## Still simulated / not enforced

See `docs/LIMITATIONS.md`. The ones that matter:

1. `key_by_surrogate=False` by default — pseudonymization exists but is off.
   Must flip to `True`, and `IDENTITY_SALT` must be set, before real data.
2. No authentication on any route (B1) — Phase 4. **Do not host publicly until
   then**: four destructive routes are open and anyone could burn the API keys.
3. Scoring is still single-point threshold logic against week 1;
   `data_quality.low_confidence` is computed but not consumed. Phase 2.
4. DB and cloud-bucket ingestion read real storage but are seeded synthetically.

## Decisions made

- **`compute_risk_index()` written but not wired in.** §4 lists "risk index" as
  domain logic, but no deterministic scorer existed — the LLM produces the score.
  Writing it additively keeps Phase 1 behaviour-preserving; Phase 6 promotes it.
- **The Phase 1 exit criterion needed amending.** "Byte-identical output from both
  entrypoints" is unachievable while a nondeterministic LLM scores. Amended to
  *identical output through a deterministic fake*, which §6.3 requires anyway.
- **Licence stays MIT.** A use-restricting licence is not OSI-approved, so GitHub
  would not call it open source and most legal teams auto-block it — defeating the
  goal of a public contribution. It also would not work in practice. The real
  controls are the runtime purpose binding and the allowlist; the README says
  plainly that a fork can strip them.
- **The `run_pipeline.py` bypass was closed early** once real data was confirmed as
  anticipated. That was the stated trigger.
- **Blocker list corrections** (Phase 0 assessment): B8 overstated — `.env` is
  gitignored with zero commits in history, so the gap is *absent secret scanning*,
  not leaked secrets. B11 imprecise — read paths are real, seeding is synthetic.
  B9 line refs drifted to `runner_helper.py:136,185-186`. B12 understated — 47
  files, not 15.

## Outstanding (asked for, not yet done)

- **GitHub Pages static showcase** — approved but not built. Static landing page
  (screenshots, architecture, the ethical framing) served from Pages. Safe because
  it has no backend. The *app* must not be hosted until Phase 4 adds auth.
- **Branch protection** — the rule was created but the required status check may
  not have been attached. Verify `check` is listed under "Require status checks" in
  Settings → Branches, and that Actions has run at least once.

## Next session

Finish Phase 1: items 1–5 under "Not done" above. Read only `src/domain/*` and
`tests/unit/` — the extraction is complete, so `app.py` and `static/index.html`
do not need to be opened.
