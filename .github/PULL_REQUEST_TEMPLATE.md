## What and why

<!-- What changes, and what problem it solves. Explain *why*, not just *what*. -->

## How it was verified

<!-- What you actually RAN, not what you reasoned about. Paste the command and
     the result. "Should work" is not verification. -->

- [ ] `uv run ruff check . && uv run ruff format --check .`
- [ ] `uv run ty check`
- [ ] `uv run pytest -m "not integration"`

## Privacy and purpose impact

This tool observes people at work. Every change is reviewed against that.

- [ ] Adds **no** new field to `config/data_allowlist.json`, **or** the new field
      has a written `rationale` *and* a `benign_explanation`
- [ ] Introduces no health, message-content, sentiment/emotion, telemetry,
      location, protected-characteristic, or compensation data
- [ ] Adds no performance/quality metric to risk scoring
- [ ] Adds no cross-employee ranking or cohort comparison of individuals
- [ ] Does not weaken purpose binding, the audit log, or retention
- [ ] If `config/data_allowlist.json` changed, `docs/NOTICE.md` was regenerated
      (`python -m src.governance.notice`) — the drift test enforces this
- [ ] Output still respects the six rules in `CONTEXT.md` (first names only,
      supportive framing, missing data as a gap, no raw provider errors,
      behavioural signals only)

> Would you be comfortable if this ran on you, and you read the audit log?
> If not, say so here rather than shipping it.

## Honesty

- [ ] Anything simulated is suffixed `_simulated`, labelled in the UI, and listed
      in `docs/LIMITATIONS.md`
- [ ] `README.md` claims still match observable behaviour
- [ ] `CHANGELOG.md` updated
- [ ] No test was weakened to make CI pass

## Anything you are unsure about

<!-- Genuinely useful. Uncertainty stated up front is cheaper than a bug found later. -->
