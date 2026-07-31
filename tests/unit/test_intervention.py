# Intervention outcome tracking -- does manager action appear to help?
#
# The tests that matter here are the ones about what the module REFUSES to do.
# Measuring "did the intervention work" is easy to build and almost always built
# wrong, in two specific ways, and both are guarded below:
#
#   1. Reporting raw before/after change, which credits every intervention with
#      regression to the mean and tells every manager they are effective.
#   2. Aggregating per manager, which turns a wellbeing tool into a performance
#      tool whose KPI is other people's wellbeing metrics.

import pytest
from pydantic import ValidationError

from src.domain.intervention import (
    DEFAULT_PERSISTENCE,
    MIN_OUTCOMES_FOR_AGGREGATE,
    MIN_POST_WEEKS,
    NEGLIGIBLE_EXCESS,
    InterventionOutcome,
    InterventionRecord,
    InterventionType,
    aggregate_by_type,
    describe_outcome,
    expected_regression_recovery,
    measure_outcome,
    persistence,
)
from src.domain.models import Confidence, MetricBaseline


def _baseline(centre=20.0, spread=4.0, observations=8):
    return MetricBaseline(centre=centre, spread=spread, observations=observations)


def _record(week=4, intervention=InterventionType.CHECK_IN):
    return InterventionRecord(subject_id="priya", week=week, intervention=intervention)


def _outcome(excess, intervention=InterventionType.CHECK_IN, subject="priya"):
    return InterventionOutcome(
        subject_id=subject,
        week=4,
        intervention=intervention,
        metric="completed_tasks",
        observed_recovery=excess + 1.0,
        expected_from_regression=1.0,
        excess_recovery=excess,
        post_weeks=3,
    )


# ---------------------------------------------------------------------------
# The guard rails
# ---------------------------------------------------------------------------
def test_intervention_module_exposes_no_manager_scoring():
    """A per-manager effectiveness number turns this into a performance tool for
    managers whose KPI is their reports' wellbeing metrics.

    The incentive that creates is immediate: a manager scored on their reports'
    numbers recovering will lean on the people whose numbers look bad. The tool
    would cause the harm it exists to prevent, through the person best placed to
    help. If a function appears here that does that, this test should fail and
    the conversation should happen.
    """
    from src.domain import intervention

    public = {name for name in dir(intervention) if not name.startswith("_")}
    for banned in ("manager", "rank", "leaderboard", "effectiveness_of", "score_for"):
        assert not any(banned in name.lower() for name in public), (
            f"src/domain/intervention.py gained manager scoring: {banned}"
        )


def test_no_intervention_record_can_carry_free_text():
    """Free text here would be the contents of a private 1-on-1."""
    fields = set(InterventionRecord.model_fields)
    for banned in ("notes", "note", "comment", "detail", "text", "said", "transcript"):
        assert banned not in fields, f"InterventionRecord gained {banned!r}"

    # Unknown keys are dropped rather than stored.
    record = InterventionRecord.model_validate(
        {
            "subject_id": "priya",
            "week": 3,
            "intervention": "check_in",
            "notes": "she said her father is ill",
        }
    )
    assert not hasattr(record, "notes")
    assert "she said" not in str(record.model_dump())


def test_every_outcome_is_marked_association_only():
    """No consumer may render this as causal. There is no control group and no
    randomisation; the flag is not assigned at random, it is assigned to the
    people who looked worst."""
    outcome = _outcome(1.5)
    assert outcome.association_only is True

    # And it cannot be turned off: the model is frozen, so a consumer cannot
    # quietly strip the caveat before rendering.
    with pytest.raises(ValidationError):
        outcome.association_only = False


# ---------------------------------------------------------------------------
# Regression to the mean -- the whole point
# ---------------------------------------------------------------------------
def test_a_useless_intervention_shows_no_excess_recovery():
    """The headline property.

    A person is flagged in their worst week and then simply reverts to their
    normal, with nobody doing anything useful. Raw before/after would call this
    a success. Excess recovery must not.
    """
    baseline = _baseline(centre=20.0, spread=4.0)
    # Ordinary noisy series, one bad week at 4, then back to normal.
    series = [
        (1, 21.0),
        (2, 19.0),
        (3, 22.0),
        (4, 10.0),  # flagged week
        (5, 20.0),
        (6, 21.0),
        (7, 19.0),
    ]

    outcome = measure_outcome(_record(week=4), "completed_tasks", baseline, series)
    assert outcome is not None
    assert outcome.observed_recovery > 0, "the person did visibly bounce back"
    assert outcome.expected_from_regression > 0, "and that was entirely expected"
    assert not outcome.is_detectable, (
        "a bounce-back that regression fully explains was reported as an effect"
    )
    assert "expected anyway" in describe_outcome(outcome)


def test_a_real_sustained_improvement_survives_the_correction():
    """The correction must not be so aggressive that nothing is ever detectable.

    Here the person does not merely revert -- they end up materially better than
    their own long-run normal and stay there.
    """
    baseline = _baseline(centre=20.0, spread=2.0)
    series = [
        (1, 20.0),
        (2, 19.0),
        (3, 20.0),
        (4, 12.0),  # flagged
        (5, 26.0),
        (6, 27.0),
        (7, 26.0),
    ]

    outcome = measure_outcome(
        _record(week=4, intervention=InterventionType.WORKLOAD_ADJUSTMENT),
        "completed_tasks",
        baseline,
        series,
    )
    assert outcome is not None
    assert outcome.is_detectable
    assert outcome.excess_recovery > 0
    assert outcome.direction == "improved"


def test_a_further_decline_is_reported_as_such():
    baseline = _baseline(centre=20.0, spread=2.0)
    series = [
        (1, 20.0),
        (2, 20.0),
        (3, 19.0),
        (4, 14.0),  # flagged
        (5, 6.0),
        (6, 5.0),
        (7, 5.0),
    ]
    outcome = measure_outcome(_record(week=4), "completed_tasks", baseline, series)
    assert outcome is not None
    assert outcome.excess_recovery < 0
    assert outcome.direction == "declined further"
    assert "worse" in describe_outcome(outcome)


def test_persistence_shapes_how_much_recovery_is_expected():
    """A person whose weeks barely correlate bounces back constantly, so a
    recovery from them means much less than the same recovery from someone
    whose weeks are strongly correlated."""
    steady = [20.0, 20.5, 21.0, 21.5, 22.0, 22.5]  # strongly autocorrelated
    jumpy = [20.0, 5.0, 21.0, 4.0, 22.0, 3.0]  # alternating

    assert persistence(steady) > persistence(jumpy)

    baseline = _baseline(centre=20.0, spread=4.0)
    assert expected_regression_recovery(8.0, baseline, jumpy) > (
        expected_regression_recovery(8.0, baseline, steady)
    )


def test_persistence_falls_back_conservatively_on_short_series():
    """Assuming low persistence would credit interventions for recoveries that
    were always going to happen."""
    assert persistence([]) == DEFAULT_PERSISTENCE
    assert persistence([1.0, 2.0]) == DEFAULT_PERSISTENCE
    assert persistence([5.0, 5.0, 5.0, 5.0, 5.0]) == DEFAULT_PERSISTENCE


def test_persistence_is_bounded():
    for series in ([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], [6.0, 1.0, 6.0, 1.0, 6.0, 1.0]):
        assert 0.0 <= persistence(series) <= 1.0


# ---------------------------------------------------------------------------
# Not enough evidence
# ---------------------------------------------------------------------------
def test_an_intervention_too_recent_to_measure_returns_nothing():
    """One week after a conversation is noise, and the honest output is silence
    rather than a number with a caveat nobody reads."""
    baseline = _baseline()
    series = [(1, 20.0), (2, 19.0), (3, 21.0), (4, 10.0), (5, 15.0)]

    assert measure_outcome(_record(week=4), "completed_tasks", baseline, series) is None
    assert MIN_POST_WEEKS == 2


def test_an_intervention_on_a_week_with_no_data_returns_nothing():
    baseline = _baseline()
    series = [(1, 20.0), (2, 19.0), (5, 18.0), (6, 20.0)]
    assert measure_outcome(_record(week=3), "completed_tasks", baseline, series) is None


def test_confidence_stays_low_on_thin_evidence():
    baseline = _baseline()
    short = [(1, 20.0), (2, 19.0), (3, 21.0), (4, 10.0), (5, 20.0), (6, 20.0)]
    outcome = measure_outcome(_record(week=4), "completed_tasks", baseline, short)
    assert outcome is not None
    assert outcome.confidence is Confidence.LOW

    long_series = [(w, 20.0) for w in range(1, 8)] + [
        (8, 10.0),
        (9, 20.0),
        (10, 20.0),
        (11, 21.0),
        (12, 20.0),
    ]
    richer = measure_outcome(_record(week=8), "completed_tasks", baseline, long_series)
    assert richer is not None
    assert richer.confidence is Confidence.MODERATE


# ---------------------------------------------------------------------------
# Aggregation, by type only
# ---------------------------------------------------------------------------
def test_a_practice_with_too_few_outcomes_is_reported_as_unevaluated():
    """Not omitted. Silently dropping it would let a reader assume it had been
    evaluated and found unremarkable."""
    aggregates = aggregate_by_type([_outcome(1.0) for _ in range(2)])
    assert len(aggregates) == 1
    assert aggregates[0].reportable is False
    assert aggregates[0].median_excess_recovery is None
    assert "Too few" in aggregates[0].note


def test_an_evaluated_practice_reports_with_its_caveat():
    outcomes = [
        _outcome(1.5, InterventionType.WORKLOAD_ADJUSTMENT)
        for _ in range(MIN_OUTCOMES_FOR_AGGREGATE)
    ]
    aggregate = aggregate_by_type(outcomes)[0]

    assert aggregate.reportable is True
    assert aggregate.sample_size == MIN_OUTCOMES_FOR_AGGREGATE
    assert aggregate.improved == MIN_OUTCOMES_FOR_AGGREGATE
    assert "Association only" in aggregate.note
    assert "not what it caused" in aggregate.note


def test_aggregation_separates_improvement_decline_and_nothing():
    outcomes = (
        [_outcome(2.0) for _ in range(3)]
        + [_outcome(-2.0) for _ in range(2)]
        + [_outcome(NEGLIGIBLE_EXCESS / 2) for _ in range(2)]
    )
    aggregate = aggregate_by_type(outcomes)[0]

    assert aggregate.improved == 3
    assert aggregate.declined == 2
    assert aggregate.no_change == 2
    assert aggregate.sample_size == 7


def test_doing_nothing_is_a_recordable_practice():
    """Without a 'no action' control, the only comparison available mixes
    'did nothing' with 'did something and forgot to log it', which biases every
    aggregate upward."""
    assert InterventionType.NO_ACTION_TAKEN in set(InterventionType)

    outcomes = [
        _outcome(0.1, InterventionType.NO_ACTION_TAKEN)
        for _ in range(MIN_OUTCOMES_FOR_AGGREGATE)
    ]
    aggregate = aggregate_by_type(outcomes)[0]
    assert aggregate.reportable is True
    assert aggregate.intervention is InterventionType.NO_ACTION_TAKEN


def test_aggregates_are_ordered_stably():
    outcomes = [
        _outcome(1.0, InterventionType.WORKLOAD_ADJUSTMENT)
        for _ in range(MIN_OUTCOMES_FOR_AGGREGATE)
    ] + [
        _outcome(1.0, InterventionType.CHECK_IN)
        for _ in range(MIN_OUTCOMES_FOR_AGGREGATE)
    ]
    names = [a.intervention.value for a in aggregate_by_type(outcomes)]
    assert names == sorted(names)
    assert aggregate_by_type([]) == []
