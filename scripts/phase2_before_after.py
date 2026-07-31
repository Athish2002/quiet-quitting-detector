#!/usr/bin/env python
"""Before/after comparison of the Phase 1 and Phase 2 detection methods.

    uv run python scripts/phase2_before_after.py

Phase 2's exit criterion (PRODUCTION_EVOLUTION_PROMPT.md 9) requires "a
documented before/after on the same fixture showing which week-3 'signals' the
new method correctly rejects as noise". This script produces that comparison, so
docs/PHASE2_BEFORE_AFTER.md is generated evidence rather than a claim, and can be
re-run against any future fixture.

BEFORE: `confirm_signals_threshold` -- fixed percentage cut-offs against week 1.
AFTER:  `confirm_signals`           -- distributional personal baseline (median
                                        and MAD) plus CUSUM change-point
                                        confirmation, with the 2+-consecutive
                                        week rule kept as a floor.

Both are pure functions over the same fixtures. Nothing here touches a network.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.domain import (
    WeekMetrics,
    confirm_signals,
    confirm_signals_threshold,
)
from src.domain.cohort import cohort_shift


def week(n: int, tasks=None, response=None, after_hours=None, hours=None):
    return WeekMetrics(
        week=n,
        completed_tasks=tasks,
        response_time=response,
        after_hours_logins=after_hours,
        weekly_hours=hours,
    )


#: Each case is (name, what-is-actually-happening, timeline).
CASES: list[tuple[str, str, list[WeekMetrics]]] = [
    (
        "Rough fortnight, then recovery",
        "A hard two weeks -- a move, a bereavement, a brutal on-call rotation -- "
        "followed by a full return to normal. Nothing about this person's work "
        "has durably changed.",
        [
            week(1, tasks=20, response=1.0, hours=40),
            week(2, tasks=13, response=1.7, hours=30),
            week(3, tasks=12, response=1.8, hours=29),
            week(4, tasks=20, response=1.1, hours=40),
            week(5, tasks=21, response=1.0, hours=41),
            week(6, tasks=20, response=1.0, hours=40),
        ],
    ),
    (
        "Naturally variable worker",
        "Output that has always swung widely, week to week, for years. Nothing "
        "has changed; this is simply what their normal looks like.",
        [
            week(1, tasks=22, response=1.0, hours=40),
            week(2, tasks=12, response=2.2, hours=32),
            week(3, tasks=21, response=1.1, hours=41),
            week(4, tasks=13, response=2.0, hours=33),
            week(5, tasks=20, response=1.2, hours=40),
            week(6, tasks=14, response=1.9, hours=34),
        ],
    ),
    (
        "Genuine sustained decline",
        "A real, durable change in engagement -- the case the system exists to "
        "notice. Any method that misses this is worthless.",
        [
            week(1, tasks=20, response=1.0, hours=40),
            week(2, tasks=17, response=1.4, hours=37),
            week(3, tasks=13, response=2.1, hours=31),
            week(4, tasks=10, response=2.8, hours=27),
            week(5, tasks=8, response=3.4, hours=24),
            week(6, tasks=7, response=3.6, hours=23),
        ],
    ),
    (
        "Abrupt shift after a steady history",
        "Someone completely consistent for months who changes sharply and stays "
        "changed. The clearest signal there is.",
        [
            week(1, tasks=15, response=2.0, hours=38),
            week(2, tasks=15, response=2.0, hours=38),
            week(3, tasks=15, response=2.1, hours=38),
            week(4, tasks=6, response=4.5, hours=22),
            week(5, tasks=5, response=4.8, hours=21),
            week(6, tasks=6, response=4.6, hours=22),
        ],
    ),
    (
        "Approved reduced hours",
        "A formally agreed drop to part-time in week 4, held steady afterwards. "
        "This is an HR arrangement, not disengagement -- but no metric in the "
        "data says so.",
        [
            week(1, tasks=20, response=1.0, hours=40),
            week(2, tasks=19, response=1.1, hours=40),
            week(3, tasks=20, response=1.0, hours=40),
            week(4, tasks=10, response=1.1, hours=20),
            week(5, tasks=10, response=1.0, hours=20),
            week(6, tasks=11, response=1.1, hours=20),
        ],
    ),
]

#: A team-wide event: everyone's task count collapses in week 3 (an outage, a
#: company offsite, a public holiday). Used to show the cohort correction.
COHORT_WEEK3 = {
    "a": 8.0,
    "b": 7.0,
    "c": 9.0,
    "d": 6.0,
    "e": 8.0,
}
COHORT_BASELINES = {"a": 20.0, "b": 18.0, "c": 21.0, "d": 16.0, "e": 19.0}


def describe(signals) -> str:
    if not signals:
        return "(none)"
    return "; ".join(
        f"{s.signal_name} [{s.severity.value}] weeks {list(s.weeks_detected)}"
        + (" (wellbeing only)" if s.wellbeing_only else "")
        for s in signals
    )


def main() -> int:
    print("=" * 78)
    print("PHASE 1 (threshold vs week 1)  ->  PHASE 2 (distribution + CUSUM)")
    print("=" * 78)

    for name, explanation, timeline in CASES:
        before = confirm_signals_threshold(timeline)
        after = confirm_signals(timeline)

        print(f"\n## {name}")
        print(f"   {explanation}")
        print(f"   BEFORE: {describe(before)}")
        print(f"   AFTER : {describe(after)}")

        before_names = {s.signal_name for s in before}
        after_names = {s.signal_name for s in after}
        dropped = sorted(before_names - after_names)
        added = sorted(after_names - before_names)
        if dropped:
            print(f"   -> rejected as noise: {', '.join(dropped)}")
        if added:
            print(f"   -> newly detected:    {', '.join(added)}")
        if not dropped and not added:
            print("   -> unchanged")

    # --- cohort confound ---------------------------------------------------
    print("\n" + "=" * 78)
    print("COHORT CONFOUND REMOVAL (fairness correction only)")
    print("=" * 78)

    shift = cohort_shift(COHORT_WEEK3, COHORT_BASELINES)
    print(f"\n   Week 3 cohort-wide proportional change: {shift:+.1%}")

    # The team's scope was cut in week 3 and stayed cut. This individual's task
    # count fell exactly as everyone else's did -- nothing about them changed.
    individual = [
        week(1, tasks=20, response=1.0, hours=40),
        week(2, tasks=19, response=1.0, hours=40),
        week(3, tasks=8, response=1.0, hours=40),
        week(4, tasks=9, response=1.0, hours=40),
        week(5, tasks=8, response=1.0, hours=40),
        week(6, tasks=9, response=1.0, hours=40),
    ]
    shared = dict.fromkeys(range(3, 7), shift)
    uncorrected = confirm_signals(individual)
    corrected = confirm_signals(individual, cohort_shifts={"completed_tasks": shared})
    print(f"   WITHOUT correction: {describe(uncorrected)}")
    print(f"   WITH correction   : {describe(corrected)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
