# Changelog

Notable changes per unit of work. Newest first.

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
