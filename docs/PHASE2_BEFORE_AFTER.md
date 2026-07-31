# Phase 2 — before and after

Phase 2's exit criterion (`PRODUCTION_EVOLUTION_PROMPT.md` §9) requires *"a
documented before/after on the same fixture showing which week-3 'signals' the new
method correctly rejects as noise."* This is it.

Everything below is **generated output**, not a description of intent. Regenerate:

```bash
uv run python scripts/phase2_before_after.py
```

Both methods are pure functions in `src/domain`, run on identical fixtures, with no
network and no LLM involved.

---

## What changed

| | Phase 1 (`confirm_signals_threshold`) | Phase 2 (`confirm_signals`) |
|---|---|---|
| Baseline | Week 1 — a **single observation** | Median + spread over the person's own earliest weeks |
| Spread | none | MAD, or median successive difference, whichever is larger |
| Test | fixed % cut-off (20% task drop, etc.) | effect size **and** materiality, both required |
| Trend vs noise | not distinguished | CUSUM change-point detection |
| 2+ consecutive weeks | the whole method | kept, as a **floor** |
| Still happening? | not checked | required — a resolved pattern is not current risk |
| Team-wide events | ignored | shared downward moves removed before judging anyone |

The two defects being fixed:

1. **Week 1 is one observation.** If someone's first week was unusually productive
   — a launch, a backlog cleared — their "baseline" is their personal best, and
   every ordinary week afterwards reads as decline. The system flagged its hardest
   workers.
2. **A fixed 20% means the same thing to everyone.** For someone whose output
   naturally swings between 8 and 20 tasks, a 20% dip is Tuesday. For someone who
   ships 12 every week without fail, it is the most unusual thing that has ever
   happened to them. One constant cannot be right for both, and the person it is
   wrong about pays for it.

---

## Case 1 — rough fortnight, then recovery ✅ **the headline result**

A hard two weeks — a move, a bereavement, a brutal on-call rotation — followed by a
full return to normal. Nothing about how this person works has durably changed.

```
tasks     20  13  12  20  21  20
response 1.0 1.7 1.8 1.1 1.0 1.0
hours     40  30  29  40  41  40
```

| | Result |
|---|---|
| **BEFORE** | `Declining Task Completion [high] weeks [2,3]`; `Reduced Working Hours [medium] weeks [2,3]`; `Response Time Spike [medium] weeks [2,3]` |
| **AFTER** | *(none)* |

**Three confirmed signals became zero.** The old method saw two consecutive weeks
past a percentage line and confirmed. CUSUM sees an excursion that returns to
baseline and does not accumulate; the sustained-pattern check independently
requires the run to still be running.

This is the case where being wrong does real damage. The person is already having
the worst month of their year, and the system's contribution was to tell their
manager they might be quitting.

## Case 2 — naturally variable worker ✅

Output that has always swung widely, week to week, for years.

```
tasks  22  12  21  13  20  14
```

| | Result |
|---|---|
| **BEFORE** | *(none)* |
| **AFTER** | *(none)* |

Both correct, but for different reasons, and the difference matters. The old
method missed it by luck — the swing happened to straddle week 1's value. The new
method models a spread of ~8 tasks and correctly reports that a swing of 10 is
this person's normal.

An earlier Phase 2 draft **did** flag this person, because MAD over three
alternating values (22, 12, 21) collapses to 1. That is why `build_baseline` takes
the larger of MAD and the median successive difference — see
`src/domain/statistics.py`. The regression was caught by
`scripts/phase2_before_after.py` before it shipped, which is the reason this
comparison is a script and not a paragraph.

## Case 3 — genuine sustained decline ✅

The case the system exists to notice.

```
tasks     20  17  13  10   8   7
response 1.0 1.4 2.1 2.8 3.4 3.6
hours     40  37  31  27  24  23
```

| | Result |
|---|---|
| **BEFORE** | `Declining Task Completion [high] weeks [3,4,5,6]`; `Reduced Working Hours [medium] weeks [4,5,6]`; `Response Time Spike [high] weeks [3,4,5,6]` |
| **AFTER** | `Declining Task Completion [medium] weeks [3,4,5,6]`; `Reduced Working Hours [medium] weeks [4,5,6]`; `Response Time Spike [medium] weeks [3,4,5,6]` |

Same signals, same weeks. **The precision was not bought by going blind.**

Severities came down from `high` to `medium`. That is the intended consequence of
grading against the person's own variability rather than against a fixed
percentage: this is a real and serious decline, and it is a *gradual* one, and the
grading now says so.

## Case 4 — abrupt shift after a steady history ✅

```
tasks     15  15  15   6   5   6
```

| | Result |
|---|---|
| **BEFORE** | `Declining Task Completion [high] weeks [4,5,6]` (+ hours, response) |
| **AFTER** | `Declining Task Completion [high] weeks [4,5,6]` (+ hours, response) |

Identical. For someone this consistent, a change this large is unambiguous under
either method, and `high` survives — a 60% drop for a person who has never varied
is exactly what a high-severity signal should mean.

## Case 5 — approved reduced hours ⚠️ **a limitation, not a fix**

A formally agreed drop to part-time in week 4, held steady afterwards.

```
tasks   20  19  20  10  10  11
hours   40  40  40  20  20  20
```

| | Result |
|---|---|
| **BEFORE** | `Declining Task Completion [high] weeks [4,5,6]`; `Reduced Working Hours [high] weeks [4,5,6]` |
| **AFTER** | `Declining Task Completion [high] weeks [4,5,6]`; `Reduced Working Hours [medium] weeks [4,5,6]` |

**Still flagged, and it should be.** No statistical method can distinguish an
approved schedule change from disengagement, because the difference is not in the
data — it is in an HR record this system deliberately does not hold.

The honest handling is not a cleverer detector. It is that the briefing is
supportive and non-disciplinary by construction, so the output of this case is a
manager having a conversation they already knew the answer to. Recorded in
`docs/LIMITATIONS.md`.

---

## Cohort confound removal

Team-wide event in week 3 — an outage, an offsite, a scope cut — that persists.
Five people, each measured against **their own** baseline; the median shared move
is **−60.0%**.

An individual whose task count fell exactly as everyone else's did:

```
tasks   20  19   8   9   8   9
```

| | Result |
|---|---|
| **WITHOUT correction** | `Declining Task Completion [low] weeks [3,4,5,6]` |
| **WITH correction** | *(none)* |

The correction is deliberately constrained, and the constraints are the design:

- It only ever computes **one number per week** describing what happened to
  everybody. There is no function in `src/domain/cohort.py` that takes an
  individual and the cohort and returns anything about that individual's standing.
  `test_cohort_module_exposes_no_per_person_comparison` fails if one appears.
- It only removes **downward** shared moves. Removing an upward one would mean
  holding people to a raised bar because their team had a good week — "everyone
  else surged and you did not" — which is a stack rank wearing a different hat.
- It can only ever **remove** a signal, never create one
  (`test_the_cohort_correction_can_only_remove_signals`).
- Below three people it is skipped entirely. Two colleagues having a bad week is
  not a company-wide event.

---

## Uncertainty

Every assessment now carries `confidence`, a `score_range`, and ranked
`attributions`. The failure this prevents is specific: a system with two patchy
weeks prints "6/10 — At Risk", a manager reads a number, and the number carries
authority the evidence never had.

`score_range` is a **heuristic band that widens as evidence thins — not a
frequentist confidence interval.** There is no sampling distribution here to derive
one from, and calling a rule of thumb a "95% CI" would be borrowed authority. The
field is named accordingly and the limitation is in `docs/LIMITATIONS.md`.
