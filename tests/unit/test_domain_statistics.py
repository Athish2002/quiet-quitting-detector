# Phase 2 -- the honest-statistics layer (PRODUCTION_EVOLUTION_PROMPT.md 6.1).
#
# Covers the four new pure modules: robust baselines, change-point detection,
# cohort confound removal, uncertainty, and attribution.
#
# The tests are written around the DECISIONS these modules make about a person,
# not around their arithmetic. "MAD of [1,2,3] is 1" is trivially true and
# proves nothing; "someone whose output has always swung widely is not flagged
# for an ordinary week" is the property that determines whether this tool is
# fair to the people it is pointed at.

import pytest

from src.domain import (
    Confidence,
    Direction,
    MetricBaseline,
    Severity,
    Signal,
    WeekMetrics,
    assess_confidence,
    assess_from_timeline,
    attribute,
    build_baseline,
    build_personal_baselines,
    cohort_shift,
    confirm_signals,
    confirm_signals_threshold,
    cusum_shift_week,
    effect_size,
    is_shared_confound,
    is_significant,
    leading_metric,
    longest_consecutive_run,
    remove_shared_confound,
    robust_z,
    score_range,
    suppresses_briefing,
)
from src.domain.changepoint import (
    CUSUM_SLACK,
    CUSUM_THRESHOLD,
    concerning_deviation,
)
from src.domain.cohort import MIN_COHORT_SIZE
from src.domain.risk import MAX_SCORE, MIN_SCORE
from src.domain.signals import (
    DECLINING_TASKS,
    RESPONSE_SPIKE,
    WORKLOAD_ELEVATION,
    baseline_window_size,
    grade_effect,
)
from src.domain.statistics import (
    MIN_OBSERVATIONS_FOR_DISTRIBUTION,
    ZERO_SPREAD_ABSOLUTE_FLOOR,
    effective_spread,
    mad_of,
    median_of,
    relative_change,
    successive_difference_spread,
)


def _week(n, tasks=None, response=None, after_hours=None, hours=None, missing=False):
    return WeekMetrics(
        week=n,
        completed_tasks=tasks,
        response_time=response,
        after_hours_logins=after_hours,
        weekly_hours=hours,
        data_missing=missing,
    )


# ---------------------------------------------------------------------------
# Robust statistics
# ---------------------------------------------------------------------------
def test_median_and_mad_handle_the_empty_case():
    assert median_of([]) is None
    assert mad_of([]) is None
    assert median_of([3.0, 1.0, 2.0]) == 2.0
    assert mad_of([1.0, 2.0, 3.0]) == 1.0


def test_mad_is_not_moved_by_a_single_catastrophic_week():
    """The property that makes MAD the right choice over standard deviation.

    One disastrous week must not inflate the spread so far that every later real
    change disappears into it -- that would make the tool fall silent exactly
    when somebody needed noticing.
    """
    steady = [20.0, 21.0, 19.0, 20.0, 21.0]
    with_disaster = [*steady, 0.0]

    import statistics as stdlib

    robust_steady = mad_of(steady)
    robust_disrupted = mad_of(with_disaster)
    assert robust_steady is not None and robust_disrupted is not None
    assert robust_disrupted <= robust_steady * 2
    assert stdlib.pstdev(with_disaster) > stdlib.pstdev(steady) * 2


def test_successive_difference_spread_needs_enough_points():
    assert successive_difference_spread([1.0]) is None
    assert successive_difference_spread([1.0, 2.0]) is None
    assert successive_difference_spread([1.0, 2.0, 3.0]) == pytest.approx(
        1.0 / 1.128, rel=1e-6
    )


def test_build_baseline_takes_the_larger_spread_estimate():
    """An alternating history must not be modelled as steady.

    22, 12, 21 has a MAD of 1 -- two values sit near each other -- while the
    person plainly moves by about 10 between weeks. Believing the 1 is what
    causes someone with a decade of this pattern to be flagged for a normal week.
    """
    baseline = build_baseline([22.0, 12.0, 21.0])
    assert baseline is not None
    assert mad_of([22.0, 12.0, 21.0]) == 1.0
    assert baseline.spread > 5.0


def test_build_baseline_reports_when_it_is_thin():
    assert build_baseline([]) is None

    thin = build_baseline([10.0, 12.0])
    assert thin is not None
    assert thin.observations == 2
    assert thin.is_distributional is False

    solid = build_baseline([10.0] * MIN_OBSERVATIONS_FOR_DISTRIBUTION)
    assert solid.is_distributional is True


def test_zero_spread_is_floored_rather_than_dividing_by_zero():
    """A perfectly steady person must not become infinitely sensitive."""
    steady = MetricBaseline(centre=20.0, spread=0.0, observations=4)
    assert effective_spread(steady) == pytest.approx(2.0)

    near_zero = MetricBaseline(centre=0.0, spread=0.0, observations=4)
    assert effective_spread(near_zero) == ZERO_SPREAD_ABSOLUTE_FLOOR

    # A one-task difference for a steady 20-a-week person is noticeable, not
    # catastrophic. Without the floor this would be division by zero.
    assert abs(robust_z(19.0, steady)) < 1.0


def test_robust_z_and_relative_change_agree_on_direction():
    baseline = MetricBaseline(centre=20.0, spread=4.0, observations=6)
    assert robust_z(10.0, baseline) < 0
    assert relative_change(10.0, baseline) < 0
    assert robust_z(30.0, baseline) > 0
    assert relative_change(30.0, baseline) > 0
    zero_centre = MetricBaseline(centre=0.0, spread=1.0, observations=4)
    assert relative_change(10.0, zero_centre) == 0.0


def test_significance_requires_both_unusual_and_material():
    """Either test alone produces a failure mode that harms somebody."""
    # Extremely steady person, trivial move: statistically wild, materially nil.
    steady = MetricBaseline(centre=100.0, spread=0.01, observations=8)
    assert robust_z(98.0, steady) < -100  # wildly "significant" on its own
    assert not is_significant(
        98.0, steady, direction=Direction.BELOW, minimum_relative_change=0.20
    )

    # Highly variable person, large move: material, but ordinary for them.
    variable = MetricBaseline(centre=20.0, spread=10.0, observations=8)
    assert relative_change(12.0, variable) < -0.20  # materially large on its own
    assert not is_significant(
        12.0, variable, direction=Direction.BELOW, minimum_relative_change=0.20
    )

    # Both: steady person, large move.
    real = MetricBaseline(centre=20.0, spread=1.0, observations=8)
    assert is_significant(
        10.0, real, direction=Direction.BELOW, minimum_relative_change=0.20
    )


def test_significance_ignores_movement_in_the_harmless_direction():
    baseline = MetricBaseline(centre=20.0, spread=1.0, observations=8)
    assert not is_significant(
        40.0, baseline, direction=Direction.BELOW, minimum_relative_change=0.20
    )
    assert not is_significant(
        20.0, baseline, direction=Direction.NONE, minimum_relative_change=0.20
    )
    assert effect_size(40.0, baseline, direction=Direction.BELOW) == 0.0
    assert effect_size(40.0, baseline, direction=Direction.NONE) == 0.0
    assert effect_size(10.0, baseline, direction=Direction.BELOW) > 0.0


# ---------------------------------------------------------------------------
# Change-point detection
# ---------------------------------------------------------------------------
def test_cusum_ignores_an_isolated_spike_but_catches_a_sustained_shift():
    baseline = MetricBaseline(centre=20.0, spread=2.0, observations=6)

    spike = [(1, 20.0), (2, 20.0), (3, 4.0), (4, 20.0), (5, 20.0), (6, 20.0)]
    sustained = [(1, 20.0), (2, 20.0), (3, 14.0), (4, 13.0), (5, 13.0), (6, 12.0)]

    assert cusum_shift_week(spike, baseline, downward=True) is None
    assert cusum_shift_week(sustained, baseline, downward=True) == 3


def test_cusum_reports_when_the_change_began_not_when_it_was_noticed():
    """A stray fraction on the accumulator must not backdate a shift.

    Reporting week 2 for a change that happened in week 4 tells a manager
    somebody has been struggling a fortnight longer than they have.
    """
    baseline = MetricBaseline(centre=20.0, spread=1.0, observations=6)
    series = [(1, 20.0), (2, 19.4), (3, 20.0), (4, 8.0), (5, 8.0), (6, 8.0)]
    assert cusum_shift_week(series, baseline, downward=True) == 4


def test_cusum_needs_a_series_and_handles_direction():
    baseline = MetricBaseline(centre=2.0, spread=0.5, observations=6)
    assert cusum_shift_week([], baseline, downward=True) is None
    assert cusum_shift_week([(1, 2.0)], baseline, downward=True) is None

    rising = [(1, 2.0), (2, 5.0), (3, 5.5), (4, 6.0)]
    assert cusum_shift_week(rising, baseline, downward=False) == 2
    # The same rise is not a downward shift.
    assert cusum_shift_week(rising, baseline, downward=True) is None


def test_concerning_deviation_signs_are_direction_aware():
    baseline = MetricBaseline(centre=10.0, spread=2.0, observations=6)
    assert concerning_deviation(6.0, baseline, downward=True) > 0
    assert concerning_deviation(6.0, baseline, downward=False) < 0
    assert concerning_deviation(10.0, baseline, downward=True) == 0.0
    assert CUSUM_SLACK < CUSUM_THRESHOLD


def test_longest_consecutive_run():
    assert longest_consecutive_run(()) == 0
    assert longest_consecutive_run((3,)) == 1
    assert longest_consecutive_run((1, 2, 5, 6, 7)) == 3
    assert longest_consecutive_run((1, 3, 5)) == 1
    assert longest_consecutive_run((2, 2, 3)) == 2


# ---------------------------------------------------------------------------
# Cohort -- fairness correction only
# ---------------------------------------------------------------------------
def test_cohort_shift_needs_a_real_cohort():
    """Two people's bad week is not a company-wide event."""
    values = {"a": 8.0, "b": 7.0}
    centres = {"a": 20.0, "b": 18.0}
    assert cohort_shift(values, centres) is None

    bigger = {"a": 8.0, "b": 7.0, "c": 9.0}
    bigger_centres = {"a": 20.0, "b": 18.0, "c": 21.0}
    assert len(bigger) >= MIN_COHORT_SIZE
    shift = cohort_shift(bigger, bigger_centres)
    assert shift is not None and shift < -0.5


def test_cohort_shift_skips_people_with_no_usable_baseline():
    values = {"a": 8.0, "b": 7.0, "c": 9.0, "d": 5.0}
    centres = {"a": 20.0, "b": 18.0, "c": 21.0, "d": 0.0}
    shift = cohort_shift(values, centres)
    assert shift is not None
    # `d` contributed nothing rather than a division by zero.
    assert cohort_shift({k: values[k] for k in "abc"}, centres) == pytest.approx(
        shift, abs=0.2
    )


def test_shared_downward_moves_are_removed_and_shared_upward_moves_are_not():
    """Correcting an upward move would hold people to a raised bar because
    their team had a good week. That is ranking wearing a different hat."""
    assert remove_shared_confound(8.0, 20.0, -0.6) > 8.0
    assert remove_shared_confound(24.0, 20.0, 0.6) == 24.0
    assert remove_shared_confound(8.0, 20.0, None) == 8.0
    assert remove_shared_confound(8.0, 0.0, -0.6) == 8.0

    # Never corrected past the person's own normal.
    assert remove_shared_confound(19.0, 20.0, -0.9) <= 20.0


def test_is_shared_confound_threshold():
    assert is_shared_confound(-0.5) is True
    assert is_shared_confound(-0.05) is False
    assert is_shared_confound(None) is False
    assert is_shared_confound(0.4) is False


def test_cohort_module_exposes_no_per_person_comparison():
    """The constraint that keeps this from becoming a stack rank.

    If a function ever appears here that takes one employee and the cohort and
    returns something about that employee's standing, this test should fail and
    the review conversation should happen.
    """
    from src.domain import cohort

    public = {name for name in dir(cohort) if not name.startswith("_")}
    for banned in ("rank", "percentile", "compare", "position", "peers", "relative_to"):
        assert not any(banned in name.lower() for name in public), (
            f"src/domain/cohort.py gained a per-person comparison: {banned}"
        )


def test_a_team_wide_drop_is_not_evidence_about_an_individual():
    """The end-to-end fairness property, through the real detector."""
    individual = [
        _week(1, tasks=20),
        _week(2, tasks=19),
        _week(3, tasks=8),
        _week(4, tasks=9),
        _week(5, tasks=8),
        _week(6, tasks=9),
    ]
    shift = cohort_shift(
        {"a": 8.0, "b": 7.0, "c": 9.0, "d": 6.0},
        {"a": 20.0, "b": 18.0, "c": 21.0, "d": 16.0},
    )

    assert confirm_signals(individual), "fixture must flag without the correction"
    corrected = confirm_signals(
        individual, cohort_shifts={"completed_tasks": dict.fromkeys(range(3, 7), shift)}
    )
    assert corrected == [], (
        "a drop the whole team shared was counted against one person"
    )


def test_the_cohort_correction_can_only_remove_signals():
    """It must never be able to manufacture one."""
    flat = [_week(n, tasks=20) for n in range(1, 7)]
    invented = confirm_signals(
        flat, cohort_shifts={"completed_tasks": dict.fromkeys(range(1, 7), -0.9)}
    )
    assert invented == []


# ---------------------------------------------------------------------------
# Uncertainty
# ---------------------------------------------------------------------------
def test_confidence_rises_with_evidence():
    assert (
        assess_confidence(
            usable_weeks=0, total_weeks=4, has_distributional_baseline=False
        )
        is Confidence.NONE
    )
    assert (
        assess_confidence(
            usable_weeks=1, total_weeks=4, has_distributional_baseline=False
        )
        is Confidence.LOW
    )
    assert (
        assess_confidence(
            usable_weeks=4, total_weeks=4, has_distributional_baseline=False
        )
        is Confidence.MODERATE
    )
    assert (
        assess_confidence(
            usable_weeks=8, total_weeks=8, has_distributional_baseline=True
        )
        is Confidence.HIGH
    )
    assert (
        assess_confidence(
            usable_weeks=4, total_weeks=4, has_distributional_baseline=True
        )
        is Confidence.MODERATE
    )
    assert (
        assess_confidence(
            usable_weeks=2, total_weeks=2, has_distributional_baseline=True
        )
        is Confidence.LOW
    )


def test_missing_weeks_cap_confidence_however_long_the_timeline():
    """Ten weeks on file with six absent is not ten weeks of evidence."""
    assert (
        assess_confidence(
            usable_weeks=4, total_weeks=10, has_distributional_baseline=True
        )
        is Confidence.LOW
    )


def test_confidence_from_a_timeline_counts_gaps_honestly():
    assert assess_from_timeline([]) is Confidence.NONE

    all_missing = [_week(n, missing=True) for n in range(1, 5)]
    assert assess_from_timeline(all_missing) is Confidence.NONE

    solid = [_week(n, tasks=20, hours=40) for n in range(1, 9)]
    assert assess_from_timeline(solid) is Confidence.HIGH

    gappy = [_week(1, tasks=20), _week(2, tasks=20)] + [
        _week(n, missing=True) for n in range(3, 9)
    ]
    assert assess_from_timeline(gappy) is Confidence.LOW


def test_score_range_widens_as_confidence_falls_and_stays_in_band():
    tight = score_range(5, Confidence.HIGH)
    loose = score_range(5, Confidence.LOW)
    assert (loose[1] - loose[0]) > (tight[1] - tight[0])

    every_level = (
        Confidence.NONE,
        Confidence.LOW,
        Confidence.MODERATE,
        Confidence.HIGH,
    )
    for confidence in every_level:
        for score in range(MIN_SCORE, MAX_SCORE + 1):
            low, high = score_range(score, confidence)
            assert MIN_SCORE <= low <= score <= high <= MAX_SCORE


def test_low_confidence_suppresses_the_briefing():
    assert suppresses_briefing(Confidence.NONE) is True
    assert suppresses_briefing(Confidence.LOW) is True
    assert suppresses_briefing(Confidence.MODERATE) is False
    assert suppresses_briefing(Confidence.HIGH) is False


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------
def test_attribution_shares_sum_to_one_and_rank_by_size():
    signals = [
        Signal(
            signal_name=DECLINING_TASKS,
            weeks_detected=(2, 3, 4),
            severity=Severity.HIGH,
        ),
        Signal(signal_name=RESPONSE_SPIKE, weeks_detected=(3,), severity=Severity.LOW),
    ]
    attributions = attribute(signals)

    assert len(attributions) == 2
    assert sum(a.contribution for a in attributions) == pytest.approx(1.0)
    assert attributions[0].contribution >= attributions[1].contribution
    assert attributions[0].metric == "completed_tasks"
    assert attributions[0].direction == "below"
    assert leading_metric(attributions) == "completed_tasks"


def test_nothing_is_attributed_when_nothing_contributed():
    assert attribute([]) == ()
    assert leading_metric(()) is None

    wellbeing_only = [
        Signal(
            signal_name=WORKLOAD_ELEVATION, weeks_detected=(2, 3), wellbeing_only=True
        )
    ]
    assert attribute(wellbeing_only) == (), (
        "a wellbeing prompt was presented as a reason for a risk score"
    )


def test_attribution_uses_the_same_arithmetic_as_the_score():
    """An explanation that drifts from the number it explains is worse than none."""
    from src.domain.risk import compute_risk_index, signal_contribution

    signals = [
        Signal(
            signal_name=DECLINING_TASKS, weeks_detected=(2, 3), severity=Severity.HIGH
        ),
        Signal(
            signal_name=RESPONSE_SPIKE, weeks_detected=(2, 3), severity=Severity.MEDIUM
        ),
    ]
    total = sum(signal_contribution(s) for s in signals)
    for attribution, signal in zip(attribute(signals), signals, strict=False):
        assert attribution.contribution == pytest.approx(
            signal_contribution(signal) / total
        )
    assert compute_risk_index(signals) >= MIN_SCORE


def test_attribution_order_is_stable_for_equal_contributions():
    signals = [
        Signal(
            signal_name=RESPONSE_SPIKE, weeks_detected=(2, 3), severity=Severity.MEDIUM
        ),
        Signal(
            signal_name=DECLINING_TASKS, weeks_detected=(2, 3), severity=Severity.MEDIUM
        ),
    ]
    first = [a.metric for a in attribute(signals)]
    second = [a.metric for a in attribute(list(reversed(signals)))]
    assert first == second


# ---------------------------------------------------------------------------
# Detection wiring
# ---------------------------------------------------------------------------
def test_baseline_window_is_half_the_history_capped_at_three():
    assert baseline_window_size(0) == 1
    assert baseline_window_size(1) == 1
    assert baseline_window_size(4) == 2
    assert baseline_window_size(6) == 3
    assert baseline_window_size(20) == 3


def test_personal_baselines_cover_every_metric_present():
    timeline = [
        _week(1, tasks=20, response=1.0, after_hours=1, hours=40),
        _week(2, tasks=19, response=1.1, after_hours=1, hours=39),
        _week(3, tasks=20, response=1.0, after_hours=1, hours=40),
    ]
    baselines = build_personal_baselines(timeline)
    assert set(baselines) == {
        "completed_tasks",
        "response_time",
        "after_hours_logins",
        "weekly_hours",
    }

    partial = build_personal_baselines([_week(1, tasks=20), _week(2, tasks=19)])
    assert set(partial) == {"completed_tasks"}
    assert build_personal_baselines([]) == {}


def test_grade_effect_bands_and_the_wellbeing_cap():
    assert grade_effect(DECLINING_TASKS, 0.5) is Severity.LOW
    assert grade_effect(DECLINING_TASKS, 2.5) is Severity.MEDIUM
    assert grade_effect(DECLINING_TASKS, 9.0) is Severity.HIGH
    # No effect size, however extreme, escalates a wellbeing prompt.
    assert grade_effect(WORKLOAD_ELEVATION, 99.0) is Severity.MEDIUM


def test_a_rough_fortnight_is_no_longer_reported_as_disengagement():
    """The headline Phase 2 result. See docs/PHASE2_BEFORE_AFTER.md.

    Someone has a hard two weeks and then returns fully to normal. The old
    method reported three confirmed signals; the new one reports none, because
    nothing about how this person works has durably changed.
    """
    timeline = [
        _week(1, tasks=20, response=1.0, hours=40),
        _week(2, tasks=13, response=1.7, hours=30),
        _week(3, tasks=12, response=1.8, hours=29),
        _week(4, tasks=20, response=1.1, hours=40),
        _week(5, tasks=21, response=1.0, hours=41),
        _week(6, tasks=20, response=1.0, hours=40),
    ]
    assert len(confirm_signals_threshold(timeline)) == 3
    assert confirm_signals(timeline) == []


def test_a_naturally_variable_worker_is_not_flagged_for_an_ordinary_week():
    timeline = [
        _week(1, tasks=22, response=1.0, hours=40),
        _week(2, tasks=12, response=2.2, hours=32),
        _week(3, tasks=21, response=1.1, hours=41),
        _week(4, tasks=13, response=2.0, hours=33),
        _week(5, tasks=20, response=1.2, hours=40),
        _week(6, tasks=14, response=1.9, hours=34),
    ]
    assert confirm_signals(timeline) == []


def test_a_genuine_sustained_decline_is_still_caught():
    """The upgrade must not have bought its precision by going blind."""
    timeline = [
        _week(1, tasks=20, response=1.0, hours=40),
        _week(2, tasks=17, response=1.4, hours=37),
        _week(3, tasks=13, response=2.1, hours=31),
        _week(4, tasks=10, response=2.8, hours=27),
        _week(5, tasks=8, response=3.4, hours=24),
        _week(6, tasks=7, response=3.6, hours=23),
    ]
    names = {s.signal_name for s in confirm_signals(timeline)}
    assert DECLINING_TASKS in names
    assert RESPONSE_SPIKE in names


def test_an_abrupt_sustained_shift_is_caught_immediately():
    timeline = [
        _week(1, tasks=15),
        _week(2, tasks=15),
        _week(3, tasks=15),
        _week(4, tasks=6),
        _week(5, tasks=5),
        _week(6, tasks=6),
    ]
    signals = confirm_signals(timeline)
    assert [s.signal_name for s in signals] == [DECLINING_TASKS]
    assert signals[0].weeks_detected == (4, 5, 6)
    assert signals[0].severity is Severity.HIGH


def test_after_hours_elevation_stays_wellbeing_only_under_the_new_method():
    timeline = [
        _week(1, after_hours=1),
        _week(2, after_hours=1),
        _week(3, after_hours=1),
        _week(4, after_hours=9),
        _week(5, after_hours=10),
        _week(6, after_hours=9),
    ]
    signals = confirm_signals(timeline)
    assert [s.signal_name for s in signals] == [WORKLOAD_ELEVATION]
    assert signals[0].wellbeing_only is True
    assert signals[0].severity is Severity.MEDIUM


def test_detection_still_requires_two_consecutive_weeks():
    """The floor survives the upgrade -- it was never the part that was wrong."""
    timeline = [
        _week(1, tasks=20),
        _week(2, tasks=20),
        _week(3, tasks=20),
        _week(4, tasks=3),
        _week(5, tasks=20),
        _week(6, tasks=20),
    ]
    assert confirm_signals(timeline) == []


def test_detection_needs_a_week_one_and_enough_of_a_series():
    assert confirm_signals([]) == []
    assert confirm_signals([_week(2, tasks=5), _week(3, tasks=4)]) == []
    assert confirm_signals([_week(1, tasks=20)]) == []
    assert confirm_signals_threshold([_week(2, tasks=5), _week(3, tasks=4)]) == []


def test_a_resolved_pattern_is_not_reported_as_current_risk():
    """Someone who declined and then recovered is not currently at risk.

    That it happened is still carried by the stored history and the recurrence
    rule. What must not happen is this week's assessment describing a month that
    is over -- that is how a tool turns somebody's worst stretch into a
    permanent mark against them.
    """
    from src.domain.changepoint import is_sustained

    assert is_sustained((), 6) is False
    assert is_sustained((4, 5, 6), 6) is True
    assert is_sustained((3, 4), 6) is False

    recovered = [
        _week(1, tasks=20),
        _week(2, tasks=20),
        _week(3, tasks=20),
        _week(4, tasks=7),
        _week(5, tasks=6),
        _week(6, tasks=7),
        _week(7, tasks=20),
        _week(8, tasks=21),
        _week(9, tasks=20),
    ]
    assert confirm_signals(recovered) == []

    # The same decline, still ongoing, is reported.
    ongoing = recovered[:6]
    assert [s.signal_name for s in confirm_signals(ongoing)] == [DECLINING_TASKS]
