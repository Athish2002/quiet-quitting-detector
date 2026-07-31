# src/domain/cohort.py
# Removing shared confounds -- and NOTHING else (spec 6.1).
#
# "Seasonality and cohort context AS A FAIRNESS CORRECTION ONLY: if the whole
#  team's tasks drop in a holiday week, an individual's drop is not a signal.
#  Never use the cohort to rank or compare individuals -- only to remove shared
#  confounds."
#
# That constraint is the entire design of this module, so it is worth being exact
# about what it forbids. Two things could be built from the same input:
#
#   ALLOWED   -- "everyone's task count fell 40% in the week of the outage, so
#                 Priya's 40% fall is not evidence about Priya."
#   FORBIDDEN -- "Priya completed fewer tasks than 80% of her team."
#
# The second is a stack rank. It is the thing that turns a wellbeing tool into a
# performance-management tool, and it is what makes people justifiably afraid of
# software like this. The functions here only ever return a SHIFT -- one number
# per week describing what happened to everybody -- and never a per-person
# comparison, position, rank or percentile. There is deliberately no function in
# this file that takes one employee and the cohort and returns anything about
# that employee's standing.
#
# The cohort shift is also computed as a median, so it describes the typical
# experience rather than being dragged around by whoever had the biggest week.

from __future__ import annotations

import statistics

#: A shift computed from fewer people than this is not a shared confound, it is
#: one or two people's week. Below this the correction is skipped entirely --
#: which is the conservative choice, since applying no correction can only ever
#: leave a signal in place, never manufacture one.
MIN_COHORT_SIZE = 3


def cohort_shift(
    week_values: dict[str, float],
    baseline_centres: dict[str, float],
) -> float | None:
    """The typical proportional change shared by everyone in a given week.

    `week_values` maps an opaque employee key to that week's value;
    `baseline_centres` maps the same keys to each person's own normal. Returns
    the median proportional change, or None when the cohort is too small for the
    number to mean anything.

    Keys are never returned and never ordered. Nothing about which person
    contributed what survives this function.
    """
    changes: list[float] = []
    for key, value in week_values.items():
        centre = baseline_centres.get(key)
        if centre is None or centre == 0:
            continue
        changes.append((value - centre) / abs(centre))

    if len(changes) < MIN_COHORT_SIZE:
        return None

    return statistics.median(changes)


def remove_shared_confound(
    observed: float,
    baseline_centre: float,
    shift: float | None,
) -> float:
    """Adjust one observation for a change everybody experienced.

    If the whole team's output fell by a third in a holiday week, an individual's
    third is explained and must not count against them. Returns the value the
    person would plausibly have shown had that week been ordinary.

    The correction is one-directional on purpose: a shared DOWNWARD move is
    removed, a shared UPWARD move is not. Removing a shared upward move would
    mean holding people to a raised bar because their team had a good week --
    "everyone else surged and you did not" -- which is ranking wearing a
    different hat.
    """
    if shift is None or shift >= 0 or baseline_centre == 0:
        return observed

    # Undo the shared proportional drop, never more than back to the baseline.
    corrected = observed - (shift * abs(baseline_centre))
    return min(corrected, baseline_centre) if baseline_centre > 0 else corrected


def is_shared_confound(shift: float | None, threshold: float = 0.15) -> bool:
    """Whether a week's cohort movement is large enough to be a real confound."""
    return shift is not None and shift <= -threshold
