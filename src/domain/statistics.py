# src/domain/statistics.py
# Robust personal baselines (PRODUCTION_EVOLUTION_PROMPT.md 6.1).
#
# What this replaces
# -----------------
# Phase 1's detection compared every week against WEEK ONE, using fixed
# percentage cut-offs: a 20% task drop was a signal, full stop. That has two
# defects that matter for a tool pointed at people.
#
#   1. Week 1 is one observation. If someone happened to have an unusually
#      productive first week -- a launch, a sprint finishing, a backlog cleared
#      -- then their "baseline" is their personal best, and every ordinary week
#      afterwards reads as decline. The system would flag its hardest workers.
#
#   2. A fixed 20% means the same thing to everyone. For someone whose weekly
#      output naturally swings between 8 and 20 tasks, a 20% dip is Tuesday. For
#      someone who ships 12 tasks every single week without fail, a 20% dip is
#      the most unusual thing that has ever happened to them. One constant cannot
#      be right for both, and the person it is wrong about pays for it.
#
# What replaces it
# ----------------
# Each person's normal is modelled as a DISTRIBUTION over their own history:
# median for the centre, MAD (median absolute deviation) for the spread. Both are
# medians, so a single extreme week moves them very little -- which is the point,
# since one extreme week is exactly what must not redefine someone's normal.
#
# Deviation is then expressed as an EFFECT SIZE -- how unusual this week is for
# this person, in units of their own variability -- instead of a percentage
# compared against a constant someone picked.
#
# Nothing here knows what a "signal" is. This module answers one question:
# how far from their own normal is this number, and how sure can we be?

from __future__ import annotations

import itertools
import statistics
from enum import StrEnum

from src.domain.models import MetricBaseline

#: Consistency constant making MAD a consistent estimator of the standard
#: deviation for normally distributed data (0.6745 = the 75th-percentile z).
#: Standard in the robust-statistics literature (Iglewicz & Hoaglin, 1993).
MAD_TO_SIGMA = 0.6745

#: |modified z| at or above this is treated as a genuine deviation rather than
#: ordinary variation. 3.5 is the Iglewicz & Hoaglin outlier cut-off. It is a
#: published, citable threshold rather than a number chosen to make a demo look
#: good -- which matters when someone asks why they were flagged.
ROBUST_Z_THRESHOLD = 3.5

#: Observations needed before a distribution is meaningful at all. Below this the
#: caller is told so (insufficient_data) rather than handed a confident number
#: built on almost nothing.
MIN_OBSERVATIONS_FOR_DISTRIBUTION = 3

#: When a person's MAD is exactly zero -- perfectly steady history -- dividing by
#: it would make any change infinitely significant, and a one-task difference
#: would read as catastrophic. The spread floor is a fraction of their own centre,
#: so "unusual for them" stays proportionate to their own scale.
ZERO_SPREAD_FLOOR_FRACTION = 0.10

#: Absolute floor for the above, for metrics whose centre is at or near zero.
ZERO_SPREAD_ABSOLUTE_FLOOR = 0.5


class Direction(StrEnum):
    """Which way a deviation runs, in plain terms."""

    ABOVE = "above"
    BELOW = "below"
    NONE = "none"


def median_of(values: list[float]) -> float | None:
    """Median, or None for an empty series. Never raises."""
    return statistics.median(values) if values else None


def mad_of(values: list[float], centre: float | None = None) -> float | None:
    """Median absolute deviation about the median.

    Chosen over standard deviation deliberately: one catastrophic week would
    inflate a standard deviation enough to hide every subsequent real change,
    which would make the tool go quiet exactly when someone needed noticing.
    """
    if not values:
        return None
    mid = statistics.median(values) if centre is None else centre
    return statistics.median([abs(v - mid) for v in values])


#: Bias-correction constant (d2 for n=2) turning a moving range into a standard
#: deviation estimate. Textbook statistical process control.
MOVING_RANGE_TO_SIGMA = 1.128


def successive_difference_spread(values: list[float]) -> float | None:
    """Volatility estimated from week-to-week movement, not from the level.

    MAD alone has a specific blind spot that matters here. Take someone whose
    output has always alternated -- 22, 12, 21, 13, 20, 14 -- and take the median
    absolute deviation of the first three: two of them sit near 21, so MAD comes
    out around 1. Their own genuine week-to-week swing of ten then reads as ten
    times their normal variation, and a person who has worked this way for years
    gets flagged for having a completely ordinary week.

    The median absolute SUCCESSIVE difference cannot be fooled that way: it asks
    how much this person moves between consecutive weeks, which is the question
    actually being asked. Returns None when there are too few points to be
    anything other than noise itself.
    """
    if len(values) < MIN_OBSERVATIONS_FOR_DISTRIBUTION:
        return None
    # The length guard above guarantees at least two differences.
    differences = [abs(b - a) for a, b in itertools.pairwise(values)]
    return statistics.median(differences) / MOVING_RANGE_TO_SIGMA


def build_baseline(values: list[float]) -> MetricBaseline | None:
    """A distributional baseline for one metric from one person's own history.

    Spread is the LARGER of the two robust estimates -- deviation about the
    centre, and week-to-week movement. Taking the larger is the cautious choice
    in the direction that matters: a wider spread means a higher bar to flag
    someone, so where the two estimates disagree the system stays quiet rather
    than guessing. A false flag costs a person their standing; a missed one costs
    a check-in that a manager could still have had anyway.

    Returns None when there is nothing to model. `is_distributional` records
    whether there were enough observations to mean anything -- callers must
    surface that rather than silently treating a two-week baseline as solid.
    """
    if not values:
        return None

    centre = statistics.median(values)
    spread = mad_of(values, centre) or 0.0

    volatility = successive_difference_spread(values)
    if volatility is not None:
        spread = max(spread, volatility)

    return MetricBaseline(
        centre=centre,
        spread=spread,
        observations=len(values),
        is_distributional=len(values) >= MIN_OBSERVATIONS_FOR_DISTRIBUTION,
    )


def effective_spread(baseline: MetricBaseline) -> float:
    """The dispersion actually used, with the zero-spread floor applied."""
    if baseline.spread > 0:
        return baseline.spread
    return max(
        abs(baseline.centre) * ZERO_SPREAD_FLOOR_FRACTION,
        ZERO_SPREAD_ABSOLUTE_FLOOR,
    )


def robust_z(value: float, baseline: MetricBaseline) -> float:
    """How unusual `value` is for this person, in units of their own spread.

    Positive means above their normal, negative below. Sign is left to the
    caller to interpret: for response time, above is the concerning direction;
    for completed tasks, below is.
    """
    spread = effective_spread(baseline)
    return MAD_TO_SIGMA * (value - baseline.centre) / spread


def relative_change(value: float, baseline: MetricBaseline) -> float:
    """Plain proportional change from the person's centre.

    Kept alongside the effect size because it is the number a manager can
    actually picture. "2.4 standard deviations below their median" is precise
    and unreadable; "about a third fewer than usual" is neither, and both belong
    in a briefing.
    """
    if baseline.centre == 0:
        return 0.0
    return (value - baseline.centre) / abs(baseline.centre)


def is_significant(
    value: float,
    baseline: MetricBaseline,
    *,
    direction: Direction,
    minimum_relative_change: float,
) -> bool:
    """Whether a deviation is both statistically unusual AND materially large.

    Both conditions are required, and each one exists to stop a different bad
    outcome:

      * effect size alone would flag a rock-steady person for a trivial wobble,
        because for them any wobble is unusual;
      * relative change alone is the Phase 1 behaviour that flagged naturally
        variable people for an ordinary week.

    Requiring both means a signal has to be strange for this person *and* big
    enough to be worth a manager's attention.
    """
    z = robust_z(value, baseline)
    change = relative_change(value, baseline)

    if direction is Direction.BELOW:
        return z <= -ROBUST_Z_THRESHOLD and change <= -minimum_relative_change
    if direction is Direction.ABOVE:
        return z >= ROBUST_Z_THRESHOLD and change >= minimum_relative_change
    return False


def effect_size(
    value: float, baseline: MetricBaseline, *, direction: Direction
) -> float:
    """Magnitude of the deviation in the concerning direction, never negative.

    0.0 when the deviation runs the harmless way, so "no evidence" and "evidence
    the other way" cannot be confused by a caller that only looks at magnitude.
    """
    z = robust_z(value, baseline)
    if direction is Direction.BELOW:
        return max(0.0, -z)
    if direction is Direction.ABOVE:
        return max(0.0, z)
    return 0.0
