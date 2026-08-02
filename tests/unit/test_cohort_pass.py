# The cohort fairness correction, from the whole-cohort pass down to the
# pipeline that calls it.
#
# Built in Phase 2, tested in Phase 2, and CALLED BY NOTHING until now -- the
# pipeline scored people one at a time, so there was nowhere for a cohort-wide
# number to come from. Tested code that no production path reaches is not a
# feature; it is a claim. These tests exist to keep it a feature.

import pytest

from src.domain import WeekMetrics
from src.domain.cohort_pass import compute_cohort_shifts


def _timeline(values: list[int | None], metric: str = "completed_tasks"):
    weeks = []
    for index, value in enumerate(values, start=1):
        if value is None:
            weeks.append(WeekMetrics(week=index, data_missing=True))
        else:
            weeks.append(WeekMetrics(week=index, **{metric: value}))
    return weeks


def test_a_team_wide_drop_is_detected_as_a_shared_shift():
    """Everyone's output halves in week 4. That is an event, not five people
    simultaneously disengaging."""
    cohort = {
        "a": _timeline([20, 20, 20, 10, 10]),
        "b": _timeline([10, 10, 10, 5, 5]),
        "c": _timeline([30, 30, 30, 15, 15]),
        "d": _timeline([16, 16, 16, 8, 8]),
    }
    shifts = compute_cohort_shifts(cohort)

    assert "completed_tasks" in shifts
    assert shifts["completed_tasks"][4] < -0.3
    # Nothing happened in the early weeks.
    assert abs(shifts["completed_tasks"].get(1, 0.0)) < 0.1


def test_the_shift_is_computed_from_personal_baselines_not_raw_values():
    """The property that keeps this from becoming a comparison between people.

    A part-time employee's 10 tasks and a full-timer's 40 are two normals, not a
    gap. Taking a median of RAW values would make the correction depend on the
    mix of contracts on the team; taking a median of each person's own
    proportional change does not.
    """
    # Wildly different absolute levels, identical proportional histories.
    cohort = {
        "part_time": _timeline([10, 10, 10, 5, 5]),
        "full_time": _timeline([40, 40, 40, 20, 20]),
        "contractor": _timeline([24, 24, 24, 12, 12]),
    }
    shifts = compute_cohort_shifts(cohort)
    week_four = shifts["completed_tasks"][4]

    # Everyone halved, so the shared shift is about -50% regardless of level.
    assert week_four == pytest.approx(-0.5, abs=0.08)


def test_no_shift_is_reported_for_a_cohort_that_is_too_small():
    """Two colleagues having a bad week is not a company-wide event."""
    cohort = {"a": _timeline([20, 20, 8]), "b": _timeline([20, 20, 8])}
    shifts = compute_cohort_shifts(cohort)
    assert shifts.get("completed_tasks", {}).get(3) is None


def test_an_empty_or_unusable_cohort_yields_nothing():
    assert compute_cohort_shifts({}) == {}
    assert compute_cohort_shifts({"a": [], "b": [], "c": []}) == {}

    all_missing = {key: _timeline([None, None, None]) for key in "abcd"}
    assert compute_cohort_shifts(all_missing) == {}


def test_the_result_contains_no_employee_identifiers():
    """CONTEXT.md rule 1 and the cohort.py constraint: the output describes
    WEEKS, not people. If a key ever leaked into it, the correction would have
    become a per-person comparison."""
    cohort = {
        "priya": _timeline([20, 20, 8, 8]),
        "ade": _timeline([18, 18, 7, 7]),
        "sam": _timeline([22, 22, 9, 9]),
        "kit": _timeline([16, 16, 6, 6]),
    }
    shifts = compute_cohort_shifts(cohort)

    rendered = repr(shifts).lower()
    for name in ("priya", "ade", "sam", "kit"):
        assert name not in rendered

    # Keys are metric names then week numbers, nothing else.
    for metric, per_week in shifts.items():
        assert isinstance(metric, str)
        assert all(isinstance(week, int) for week in per_week)


def test_a_person_who_did_not_move_is_unaffected_by_a_team_wide_drop():
    """The correction must not penalise somebody for holding steady while
    everyone else fell -- that would be ranking, inverted."""
    from src.domain import confirm_signals

    steady = _timeline([20, 20, 20, 20, 20, 20])
    cohort = {
        "steady": steady,
        "b": _timeline([20, 20, 20, 8, 8, 8]),
        "c": _timeline([18, 18, 18, 7, 7, 7]),
        "d": _timeline([22, 22, 22, 9, 9, 9]),
    }
    shifts = compute_cohort_shifts(cohort)

    assert confirm_signals(steady, cohort_shifts=shifts) == []


# ---------------------------------------------------------------------------
# The wiring -- does the pipeline actually use it?
# ---------------------------------------------------------------------------
def test_the_detector_accepts_and_applies_cohort_shifts(monkeypatch):
    # §6.3: CI must never call a real LLM. Without this the enrichment step
    # reaches Gemini as soon as a signal is confirmed.
    import src.trend_detector_agent as trend_module
    from src.domain import FakeTrendEnricher
    from src.trend_detector_agent import detect_trends

    monkeypatch.setattr(trend_module, "DEFAULT_ENRICHER", FakeTrendEnricher())

    declining = [
        {"week": 1, "completed_tasks": 20},
        {"week": 2, "completed_tasks": 19},
        {"week": 3, "completed_tasks": 8},
        {"week": 4, "completed_tasks": 9},
        {"week": 5, "completed_tasks": 8},
        {"week": 6, "completed_tasks": 9},
    ]

    uncorrected = detect_trends("Priya", declining)
    assert uncorrected, "fixture must flag without the correction"

    corrected = detect_trends(
        "Priya",
        declining,
        cohort_shifts={"completed_tasks": dict.fromkeys(range(3, 7), -0.6)},
    )
    assert corrected == [], "the detector ignored the cohort correction"


def test_the_orchestrator_computes_shifts_before_scoring_anybody():
    """The wiring that took two phases to become possible.

    Asserted on the source rather than by running the pipeline: running it needs
    an LLM. What matters is that the cohort pass happens ONCE, before the
    per-employee loop -- computing it inside the loop would be both wrong and
    quadratic.
    """
    import inspect

    from src import orchestrator_agent

    source = inspect.getsource(orchestrator_agent.run_orchestrator)

    assert "compute_cohort_shifts" in source, (
        "the orchestrator no longer computes cohort shifts"
    )
    assert "cohort_shifts=cohort_shifts" in source, (
        "cohort shifts are computed but never passed to the detector"
    )

    computed_at = source.index("compute_cohort_shifts")
    loop_at = source.index("for first_name, weeks_data in employee_records.items()")
    assert computed_at < loop_at, (
        "cohort shifts are computed inside the per-employee loop; they must be "
        "computed once for the whole cohort first"
    )


def test_a_failure_in_the_cohort_pass_does_not_stop_the_run():
    """No correction is the safe degradation: a shift can only ever REMOVE a
    signal, so running without one is conservative rather than dangerous."""
    import inspect

    from src import orchestrator_agent

    source = inspect.getsource(orchestrator_agent.run_orchestrator)
    block = source[source.index("compute_cohort_shifts") - 200 :][:600]
    assert "except Exception" in block, (
        "a failure computing cohort shifts would abort the whole cohort run"
    )
