# Changelog

Notable changes per unit of work. Newest first.

## Phase 1 (in progress) — extract the domain

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

*Still open in Phase 1: property tests, import-linter contract, domain coverage
gate, agent Protocols + deterministic fake, and the parity proof.*

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
