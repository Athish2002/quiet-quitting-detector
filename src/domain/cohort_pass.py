# src/domain/cohort_pass.py
# Computing the shared confound across a whole cohort, in one pass.
#
# `cohort.py` holds the arithmetic for one metric in one week. This is the part
# that walks everybody, and it is separate because it is the piece that needs
# the WHOLE cohort in hand -- which is why the correction sat built, tested and
# uncalled for two phases: the pipeline scored people one at a time, and there
# was nowhere for a cohort-wide number to come from.
#
# The constraint from cohort.py carries through unchanged: what comes out is one
# number per metric per week describing what happened to EVERYBODY. No employee
# key appears in the result, nothing is ranked, and nothing here can tell you
# how one person compares to another. A shift can only ever REMOVE a signal.

from __future__ import annotations

from src.domain.cohort import cohort_shift
from src.domain.models import WeekMetrics
from src.domain.signals import METRIC_DIRECTION, build_personal_baselines


def compute_cohort_shifts(
    timelines: dict[str, list[WeekMetrics]],
) -> dict[str, dict[int, float]]:
    """metric -> week -> the proportional move the cohort shared that week.

    `timelines` maps an opaque employee key to that person's own weeks. The keys
    are used to iterate and are never returned: the output describes weeks, not
    people.

    Each person is measured against THEIR OWN baseline first, and only then is
    the median of those personal changes taken. Taking a median of raw values
    instead would make the correction a comparison between people, which is the
    thing this must never become -- a part-time employee's 20 tasks and a
    full-time colleague's 40 would look like a gap rather than two normals.
    """
    if not timelines:
        return {}

    baselines = {
        key: build_personal_baselines(timeline) for key, timeline in timelines.items()
    }

    weeks: set[int] = {
        week.week
        for timeline in timelines.values()
        for week in timeline
        if week.is_usable
    }

    shifts: dict[str, dict[int, float]] = {}

    for metric in METRIC_DIRECTION:
        per_week: dict[int, float] = {}

        for week_number in sorted(weeks):
            values: dict[str, float] = {}
            centres: dict[str, float] = {}

            for key, timeline in timelines.items():
                baseline = baselines[key].get(metric)
                if baseline is None:
                    continue
                observed = next(
                    (
                        getattr(week, metric)
                        for week in timeline
                        if week.week == week_number
                        and week.is_usable
                        and getattr(week, metric, None) is not None
                    ),
                    None,
                )
                if observed is None:
                    continue
                values[key] = float(observed)
                centres[key] = baseline.centre

            shift = cohort_shift(values, centres)
            if shift is not None:
                per_week[week_number] = shift

        if per_week:
            shifts[metric] = per_week

    return shifts
