# Contributing

Thanks for considering a contribution to the Quiet-Quitting Detector. This is a small, single-maintainer project -- keep changes focused and this stays easy for everyone.

## Dev setup

```bash
git clone https://github.com/Athish2002/quiet-quitting-detector.git
cd quiet-quitting-detector
cp .env.example .env      # add your own Gemini API key
uv sync --group dev
uv run uvicorn app:app --port 8000 --reload
```

## Before opening a PR

```bash
uv run pytest tests/unit   # unit tests must pass
uv run ruff check .        # lint must be clean
```

If you touch `static/index.html`, sanity-check the inline JavaScript syntax (no build step exists to catch this otherwise):
```bash
python -c "import re; open('scratch.js','w',encoding='utf-8').write(re.search(r'<script>(.*)</script>', open('static/index.html',encoding='utf-8').read(), re.S).group(1))"
node --check scratch.js && rm scratch.js
```

## Code style

* Follow the patterns already in the file you're editing over introducing a new one.
* No dead code, no speculative abstractions for a single call site, no comments that restate what the code already says.
* Keep the STRIDE-hardening rules in `CONTEXT.md` intact: first names only, no disciplinary-action language, no raw API errors surfaced to the user, no personal/health data stored.
* New ingestion sources or agent logic should degrade gracefully when the Gemini API is unavailable, consistent with the existing local-fallback tiers in `risk_scorer_agent.py` / `manager_briefing_agent.py`.

## Reporting issues

Open a GitHub issue with reproduction steps. If it's security-related, please see `THREAT_MODEL.md` first to check whether it's a known, already-mitigated class of issue.

## Pull requests

* One logical change per PR.
* Add or update a unit test in `tests/unit/` for any behavior change.
* Update `README.md` if you add or change a user-facing feature -- stale docs are worse than no docs.
