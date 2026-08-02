# PROGRESS

Read this first, update it last. Current state only — history lives in `CHANGELOG.md`.

**Phases 0–6 are complete.** The required track of `PRODUCTION_EVOLUTION_PROMPT.md`
§9 is done. What remains is the optional track (O1–O4) and the gaps below.

**CI is green on `main`** — all three jobs (`check`, `web`, `e2e`). Local `main`
and `origin/main` are in sync and the tree is clean.

| Gate | State |
|---|---|
| `ruff check` / `ruff format --check` | pass |
| `ty check` | pass |
| Unit tests | **416 pass** |
| Generated API client is not stale (CI diffs `schema.ts`) | pass |
| `domain` dependency contract | pass |
| `domain` coverage (≥95% floor) | **99.3%** |
| Agent eval (9 accuracy + 6 safety, blocking) | 15/15 |
| Frontend `tsc --noEmit` strict + vitest + axe | 24 pass |
| Playwright E2E vs the composed stack | 9 pass |
| `gitleaks` over full history | clean |

---

## What this system is now

Weekly engagement telemetry → per-person evaluation against **their own** history
→ a supportive prompt for a conversation. Six ingest paths, a pure `src/domain/`
decision layer, LLM-backed agents behind Protocols, default-deny auth, and a
React SPA.

The parts that took the most care, and why:

- **`src/domain/`** is pure and import-contracted. Both entrypoints share it, so
  the CLI and the API cannot drift (blocker B6, proven by a parity test).
- **Detection is distributional** — median + robust spread, effect size, CUSUM
  change-point detection, a sustained-pattern requirement, and a cohort confound
  correction. Evidence in `docs/PHASE2_BEFORE_AFTER.md`.
- **Uncertainty is structural.** At low confidence the score is not rendered as a
  number anywhere. `score_range` is deliberately *not* called a confidence
  interval.
- **The system can learn it was wrong** — manager feedback, calibration, a model
  registry whose promotion gate blocks *any* increase in harm regardless of
  precision gains.
- **Auth is default-deny middleware**, not per-route decorators, because B1
  happened when a route was simply not on anyone's list.

## What it refuses to do, structurally

Each of these is enforced by a test that fails if the refusal is removed:

- No ranking. `cohort.py` and `intervention.py` have no per-person or
  per-manager comparison function, and tests fail if one appears.
- No free text about a person, anywhere in feedback or interventions — there is
  no column for it.
- No manager scoring. A per-manager effectiveness number would make this a
  performance tool whose KPI is other people's wellbeing metrics.
- Intervention outcomes are `association_only` on a frozen model, corrected for
  regression to the mean. Raw before/after would tell every manager their
  interventions work, be believed, and be wrong.
- Analysing what a manager *said* is **not built** and the reasoning is at the
  top of `src/domain/intervention.py`. It needs the contents of a private 1-on-1.

---

## Known gaps (full list in `docs/LIMITATIONS.md`)

1. **`key_by_surrogate=False` by default** — pseudonymization exists but is off.
   Flip to `True` with `IDENTITY_SALT` set before any real data.
2. **Rate limiting is in-process** — multi-worker deployments multiply the
   effective limit by the worker count. Redis is O1.
3. **Config is not a validated `Settings` model** (§4). Env vars are read ad hoc.
4. **Synthetic data is reproducible but unlabelled** — no `origin='synthetic'`
   row tag, no UI banner, no `ALLOW_SYNTHETIC_DATA` production guard.
5. **Three legacy files are over the 400-line limit**, on an explicit exception
   list in `tests/unit/test_structure.py` that can only shrink:
   `risk_scorer_agent.py`, `run_pipeline.py`, `runner_helper.py`.
6. **`src/fast_api_app.py` needs GCP credentials to import**, which is why
   `tests/integration/test_server_e2e.py` cannot run here.
7. Deferred from §7 on purpose: subject-access export route, delete-by-employee,
   scheduled retention purge, key rotation.
8. CI still lacks the ≥80% overall coverage ratchet and the Docker + `trivy`
   scan.
9. **Three report routes are file downloads**, so the generated client types
   their bodies as `unknown`. No page calls them.

## Environment constraints (real, and they shape the choices)

- **Python dependencies cannot be installed.** PyPI is reachable but `uv` is
  firewall-blocked from binding a socket, and the venv has no `pip`. That is why
  `hypothesis`, `pytest-cov` and `import-linter` are implemented on the standard
  library instead — a gate that cannot be installed is a gate that never runs.
  All three are drop-in replaceable.
- **npm works**, which is what made the frontend feasible.
- **GitHub Actions logs need admin rights** this token does not have, so CI
  failures have to be reproduced locally rather than read.

---

## Next session

Nothing is half-finished; pick whichever is most valuable.

**Highest value for a reviewer:** gap 3 — a validated `Settings` model that
fails fast on bad config (§4). It is the last place the system trusts input it
has not checked.

**Then, in rough order:**
- Gap 4 — the §5 synthetic-data work: row tagging, UI banner, production guard.
- Gap 5 — split `risk_scorer_agent.py` (the fallback tiers want their own
  module) and `run_pipeline.py` (rendering split from driving).
- O1 — Postgres behind the repository interfaces.

**Outstanding asks from earlier sessions**, neither started:
- GitHub Pages static showcase (approved; safe because it has no backend).
- Verify branch protection lists `check` under required status checks.

## Working notes for whoever picks this up

- `data/memory/` was cleared twice during debugging and reseeded. It is
  gitignored and regenerable via `POST /api/v1/mock-data`.
- The demo cohort is now **seeded**, so regenerating it produces byte-identical
  CSVs and no spurious diff. Pass `{"seed": N}` for a different cohort.
- To drive the API locally: start the server, take the temporary admin key it
  prints at startup, and send `Authorization: Bearer <key>`.
- `tests/unit/conftest.py` blocks every LLM seam by default. A test that wants
  the provider path must stub it explicitly.
- **After changing any response model, regenerate the client** or CI fails:
  `uv run python scripts/export_openapi.py && npm --prefix frontend run generate:api`.
- Response models live in `src/api/schemas/`, not beside the handlers — one
  module of them was 419 lines and the 400-line gate is not negotiable.
