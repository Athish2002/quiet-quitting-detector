# CLAUDE.md — Project Operating Instructions

## Authoritative documents
- `PRODUCTION_EVOLUTION_PROMPT.md` — the spec. Binding. Read it before any work.
- `SESSION_PLAYBOOK.md` — how to run a session under a limited budget. Follow it.
- `PROGRESS.md` — current state. Read it first, update it last, every session.
- `CONTEXT.md` — six ethical rules. Non-negotiable, they override anything else here.

## Project
`quiet-quitting-detector` — multi-agent employee disengagement detection. FastAPI + Google ADK +
scikit-learn backend, migrating to a React/TypeScript frontend. Evaluates each employee against
their **own** baseline, never a cohort average. Supportive briefings only; never disciplinary.

## Hard rules
1. First names only in output. Never surnames or employee IDs.
2. Never recommend disciplinary action.
3. Missing data is a noted gap, never inferred as disengagement.
4. Never surface raw provider/API errors to users.
5. Agent memory holds behavioural signals only — no health data, no character judgements.
6. `config/data_allowlist.json` is default-deny and is the source of truth for what may be
   persisted. `docs/NOTICE.md` is generated from it and must never drift.

## Working agreement
- **One session = one task = one commit.** End green: lint, types, tests all passing.
- **Read only what you need.** Do not read `app.py` or `static/index.html` in full more than once
  per session. Never read `uv.lock`, `.venv/`, `__pycache__/`, `*.jpg`.
- **Run the checks yourself** and iterate to green before reporting back. Do not hand me failing
  code with a description of what's wrong.
- **Never weaken a test to make it pass.** Fix the code, or explain why the test was wrong.
- **Never claim something works that you did not run.** State what you executed vs. reasoned.
- **Anything simulated** gets a `_simulated` suffix in code, a label in the UI, and a line in
  `docs/LIMITATIONS.md`. `README.md` claims must match observable behaviour.
- **No new dependency** without a justification in the commit message.
- **Stop and ask** when blocked or ambiguous, with a concrete recommendation — do not guess and
  build in the wrong direction.

## Commands
```bash
uv sync                       # install
uv run uvicorn app:app --port 8000
uv run pytest tests/unit      # fast
uv run pytest                 # full
uv run ruff check . && uv run ruff format --check .
uv run ty check
```

## Current phase
See `PROGRESS.md`. If it does not exist yet, we are at Phase 0.
