# src/domain/changepoint.py
# Separating a regime shift from a bad week (PRODUCTION_EVOLUTION_PROMPT.md 6.1).
#
# The 2+-consecutive-week rule is a good floor and a poor method. It cannot tell
# the difference between:
#
#   A. someone who has genuinely, durably changed how they work, and
#   B. someone who had a rough fortnight -- a move, a bereavement, a brutal
#      on-call rotation, flu -- and then went straight back to normal.
#
# Both look identical to a consecutive-week counter, and the tool would report
# both the same way to a manager. B is the case where being wrong does real
# damage, because the person is already having the worst month of their year and
# the system's contribution is to tell their manager they might be quitting.
#
# CUSUM (cumulative sum control chart, Page 1954) is the standard, boring tool
# for this. It accumulates small deviations in one direction and signals when the
# running total exceeds a threshold, which makes it sensitive to a SUSTAINED
# small shift while ignoring isolated spikes -- exactly the distinction above.
# It is chosen over a Bayesian online change-point detector because it has two
# parameters instead of a prior, and every one of its decisions can be explained
# to the person it was applied to.
#
# This module never decides anything about an employee. It answers: did this
# series shift level, and if so, when.

from __future__ import annotations

import itertools

from src.domain.models import MetricBaseline
from src.domain.statistics import effective_spread

#: Slack, in units of the series' own spread. Deviations smaller than this are
#: absorbed as ordinary variation and never accumulate. Half a spread unit is
#: the conventional default for detecting a one-unit shift.
CUSUM_SLACK = 0.5

#: Decision threshold, in the same units. 4-5 is the standard range; 5 is the
#: conservative end, chosen because a false positive here is a false accusation
#: and a false negative is a missed check-in. Those costs are not symmetric.
CUSUM_THRESHOLD = 5.0

#: A shift must persist at least this many weeks to count as a regime change.
MIN_SHIFT_WEEKS = 2


def concerning_deviation(
    value: float, baseline: MetricBaseline, *, downward: bool
) -> float:
    """How far into the concerning direction a value sits, in spread units.

    Positive means concerning, negative means the harmless direction. Having one
    definition of "concerning" shared by the detector and the week-selection
    keeps the reported weeks consistent with the weeks that actually triggered.
    """
    spread = effective_spread(baseline)
    standardised = (value - baseline.centre) / spread
    return -standardised if downward else standardised


def cusum_shift_week(
    series: list[tuple[int, float]],
    baseline: MetricBaseline,
    *,
    downward: bool,
) -> int | None:
    """The week a sustained level shift begins, or None if there is no shift.

    `series` is (week, value) in chronological order. `downward` selects the
    concerning direction: falling task counts, or rising response times.

    Returns the week the shift STARTED, not the week the accumulator crossed its
    threshold -- a manager needs to know when things changed, not when the
    arithmetic noticed. The start is found by walking back from the crossing
    while weeks remain materially on the concerning side, rather than by
    remembering where the accumulator first left zero. The difference is not
    cosmetic: a single ordinary week can leave a fraction on the accumulator
    that never quite decays, and reporting that week as the start would tell a
    manager somebody changed a month before they actually did.
    """
    if len(series) < MIN_SHIFT_WEEKS:
        return None

    deviations = [
        (week, concerning_deviation(value, baseline, downward=downward))
        for week, value in series
    ]

    accumulated = 0.0
    for index, (_week, deviation) in enumerate(deviations):
        accumulated = max(0.0, accumulated + deviation - CUSUM_SLACK)

        if accumulated < CUSUM_THRESHOLD:
            continue

        start = index
        while start > 0 and deviations[start - 1][1] > CUSUM_SLACK:
            start -= 1

        if index - start + 1 >= MIN_SHIFT_WEEKS:
            return deviations[start][0]

        # One catastrophic week can push the accumulator over the threshold on
        # its own -- a single week bad enough to be worth ten ordinary ones. That
        # is not a regime change, it is a person having the worst week of their
        # year, and it is the case where reporting it as disengagement does the
        # most damage. Discard the accumulation and keep looking: if the shift is
        # real it will build again from the weeks that follow.
        accumulated = 0.0

    return None


def is_sustained(weeks_detected: tuple[int, ...], total_weeks: int) -> bool:
    """Whether a detected run reaches the end of the observed period.

    A pattern that stopped is a pattern that resolved. Continuing to report it as
    current risk is how a tool turns someone's worst month into a permanent mark.
    """
    if not weeks_detected:
        return False
    return max(weeks_detected) >= total_weeks


def longest_consecutive_run(weeks: tuple[int, ...]) -> int:
    """Length of the longest consecutive run in a set of week numbers."""
    if not weeks:
        return 0
    ordered = sorted(set(weeks))
    best = current = 1
    for previous, week in itertools.pairwise(ordered):
        current = current + 1 if week == previous + 1 else 1
        best = max(best, current)
    return best
