# PROGRESS

Read this first, update it last. Current state only — history lives in `CHANGELOG.md`.

**Current phase: Phase 0 complete → Phase 1 next.**

---

## Shipped (Phase 0 — Stabilise)

- **Green CI.** `.github/workflows/ci.yml` runs ruff check, ruff format --check,
  `ty`, and `pytest -m "not integration"` on push/PR. Dependencies installed with
  `uv sync --frozen` so a dependency change cannot land without its lockfile.
- **All four gates green locally**: 44 files formatted, ruff clean, `ty` clean,
  **196 unit tests pass** (6 integration deselected).
- **Fixed a `ty` error** in `governance/notice.py` (enum iteration).
- **Integration tests marked, not deleted.** `tests/integration/` needs a live LLM
  and GCP credentials, so it is `@pytest.mark.integration` and excluded from CI per
  §6.3. It fails in this environment for that reason — pre-existing, not a regression.
- **`docs/LIMITATIONS.md` created** — the honest inventory of what is simulated.
- **README overclaim fixed (B11).** Three "six genuinely working sources / not demo
  stubs" claims corrected to match observable behaviour.
- **Working tree committed** in coherent commits (B12).

Carried in from the prior session (now committed): governance package (allowlist,
audit, purpose, retention, notice), identity resolution + pseudonymization,
tolerant value coercion, week-bounds validation, atomic pipeline-slot reservation,
locked/atomic API metrics, multi-provider LLM fallback (Gemini → Groq → Ollama).

## Still simulated / not enforced

See `docs/LIMITATIONS.md` for the full list. The ones that matter most:

1. **`run_pipeline.py` bypasses governance** — still reads `sick_days` (health
   data), still keys identity on first name, still defaults missing to `0`. This is
   B6 (duplicated logic) manifesting as a compliance hole. **Do not run it against
   real data.** Fixed by Phase 1's exit criterion.
2. Prohibited columns still written to `data/weekly/*.csv` by the mock generator.
3. `key_by_surrogate=False` by default — pseudonymization exists but is off.
4. No authentication on any route (B1) — Phase 4.
5. Scoring is still single-point threshold logic; `low_confidence` is computed but
   not consumed. Phase 2.

## Decisions made

- **Phase 0 did not fix the `run_pipeline.py` hole.** §9 requires Phase 0 to be
  "no behaviour change", and the correct fix is Phase 1's domain extraction, which
  deletes the duplicate rather than patching it. Documented in `LIMITATIONS.md`
  instead of hidden. *Revisit if real data is introduced sooner than Phase 1.*
- **CI Phase-0 scope is lint/type/test only.** The other §8 gates (coverage ratchet,
  gitleaks, import-linter, Docker/trivy, Playwright, eval gate) attach to phases
  that create what they check.
- **Blocker list corrections** (evidence in session assessment): B8 overstated —
  `.env` is gitignored with zero commits in history, so the gap is *absent secret
  scanning*, not leaked secrets. B11 imprecise — read paths are real, seeding is
  synthetic. B9 line refs drifted to `runner_helper.py:136,185-186`. B12 understated
  — 47 files, not 15.

## Next — Phase 1: extract the domain

Per `SESSION_PLAYBOOK.md` Session 2. Read `src/risk_scorer_agent.py` and
`src/trend_detector_agent.py` only. Extract baselining, signal confirmation, risk
index, and healthy-streak decay into `src/domain/` (pure, no I/O, no LLM, no
framework imports) with Pydantic models. Plan first, max 10 bullets, no edits until
approved.

**Exit:** ≥95% coverage on `src/domain/`; `app.py` and `run_pipeline.py` both call it
and produce byte-identical output on `data/weekly/*.csv`, proven by diffing. That
exit criterion also closes gaps 1 and 2 above.
