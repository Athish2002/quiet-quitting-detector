# Edge-case coverage for src/domain.
#
# The property tests in test_domain_properties.py cover the universal claims.
# This file covers the specific branches they cannot reach reliably: severity
# grading boundaries, the wellbeing cap, degenerate baselines, and the fakes.
#
# Together these are what the >=95% gate in scripts/domain_coverage.py measures.

from src.domain import (
    Baseline,
    FakeRiskScorer,
    FakeTrendEnricher,
    HistoryRecord,
    RiskScorer,
    Severity,
    Signal,
    TrendEnricher,
    WeekMetrics,
    apply_recurrence_bonus,
    assign_severity,
    classify,
    confirm_consecutive,
    confirm_signals,
    detect_week_flags,
)
from src.domain.risk import MAX_SCORE, MIN_SCORE, compute_risk_index
from src.domain.signals import (
    DECLINING_TASKS,
    REDUCED_HOURS,
    RESPONSE_SPIKE,
    WORKLOAD_ELEVATION,
)


def _week(week: int, **kw) -> WeekMetrics:
    return WeekMetrics(week=week, **kw)


# ---------------------------------------------------------------------------
# Bands
# ---------------------------------------------------------------------------
def test_every_band_boundary():
    assert classify(1) == "Healthy"
    assert classify(3) == "Healthy"
    assert classify(4) == "Watch"
    assert classify(5) == "Watch"
    assert classify(6) == "At Risk"
    assert classify(7) == "At Risk"
    assert classify(8) == "Silent Exit"
    assert classify(10) == "Silent Exit"


def test_recurrence_bonus_is_capped_and_optional():
    assert apply_recurrence_bonus(5, apply=True) == 6
    assert apply_recurrence_bonus(5, apply=False) == 5
    assert apply_recurrence_bonus(MAX_SCORE, apply=True) == MAX_SCORE
    assert apply_recurrence_bonus(MIN_SCORE, apply=False) == MIN_SCORE


def test_risk_index_applies_history_when_given():
    signals = [Signal(signal_name=DECLINING_TASKS, severity=Severity.MEDIUM)]
    elevated = [
        HistoryRecord(score=7, classification="At Risk"),
        HistoryRecord(score=6, classification="Watch"),
    ]
    assert compute_risk_index(signals, elevated) > compute_risk_index(signals)
    assert compute_risk_index(signals, []) == compute_risk_index(signals)


# ---------------------------------------------------------------------------
# Severity grading
# ---------------------------------------------------------------------------
def test_task_drop_severity_boundaries():
    baseline = Baseline(completed_tasks=20)
    timeline = [
        _week(1, completed_tasks=20),
        _week(2, completed_tasks=16),  # 20% drop -> medium
        _week(3, completed_tasks=12),  # 40% drop -> high
        _week(4, completed_tasks=19),  # 5%  drop -> low
    ]
    assert assign_severity(DECLINING_TASKS, [2], timeline, baseline) == Severity.MEDIUM
    assert assign_severity(DECLINING_TASKS, [3], timeline, baseline) == Severity.HIGH
    assert assign_severity(DECLINING_TASKS, [4], timeline, baseline) == Severity.LOW


def test_response_time_severity_boundaries():
    baseline = Baseline(response_time=2.0)
    timeline = [
        _week(1, response_time=2.0),
        _week(2, response_time=3.2),  # +60%  -> medium
        _week(3, response_time=4.5),  # +125% -> high
        _week(4, response_time=2.2),  # +10%  -> low
    ]
    assert assign_severity(RESPONSE_SPIKE, [2], timeline, baseline) == Severity.MEDIUM
    assert assign_severity(RESPONSE_SPIKE, [3], timeline, baseline) == Severity.HIGH
    assert assign_severity(RESPONSE_SPIKE, [4], timeline, baseline) == Severity.LOW


def test_reduced_hours_severity_boundaries():
    baseline = Baseline(weekly_hours=40.0)
    timeline = [
        _week(1, weekly_hours=40.0),
        _week(2, weekly_hours=28.0),  # -30% -> medium
        _week(3, weekly_hours=18.0),  # -55% -> high
        _week(4, weekly_hours=38.0),  # -5%  -> low
    ]
    assert assign_severity(REDUCED_HOURS, [2], timeline, baseline) == Severity.MEDIUM
    assert assign_severity(REDUCED_HOURS, [3], timeline, baseline) == Severity.HIGH
    assert assign_severity(REDUCED_HOURS, [4], timeline, baseline) == Severity.LOW


def test_workload_elevation_is_capped_at_medium():
    """Working long hours is never allowed to grade as high severity."""
    baseline = Baseline(after_hours_logins=1, weekly_hours=40.0)
    timeline = [
        _week(1, after_hours_logins=1, weekly_hours=40.0),
        _week(2, after_hours_logins=40, weekly_hours=90.0),
    ]
    assert (
        assign_severity(WORKLOAD_ELEVATION, [2], timeline, baseline) == Severity.MEDIUM
    )


def test_severity_defaults_to_medium_for_unknown_or_absent_baseline():
    assert (
        assign_severity("Unrecognised Signal", [2], [], Baseline()) == Severity.MEDIUM
    )
    assert assign_severity(DECLINING_TASKS, [2], [], Baseline()) == Severity.MEDIUM
    assert assign_severity(REDUCED_HOURS, [2], [], Baseline(weekly_hours=40.0)) == (
        Severity.MEDIUM
    )


# ---------------------------------------------------------------------------
# Degenerate baselines
# ---------------------------------------------------------------------------
def test_zero_and_absent_baselines_never_flag():
    """A zero baseline cannot produce a percentage drop, and must not divide."""
    baseline = Baseline(
        completed_tasks=0, response_time=0.0, after_hours_logins=None, weekly_hours=0.0
    )
    timeline = [
        _week(1),
        _week(2, completed_tasks=0, response_time=0.0, weekly_hours=0.0),
    ]
    assert detect_week_flags(timeline, baseline)[2] == []


def test_partial_metrics_flag_only_what_is_present():
    baseline = Baseline(completed_tasks=20, weekly_hours=40.0)
    timeline = [
        _week(1, completed_tasks=20, weekly_hours=40.0),
        _week(2, completed_tasks=10),  # hours absent -> no hours flag
    ]
    flags = detect_week_flags(timeline, baseline)[2]
    assert flags == [DECLINING_TASKS]


def test_increased_hours_reports_as_wellbeing_not_reduction():
    baseline = Baseline(weekly_hours=40.0)
    timeline = [_week(1, weekly_hours=40.0), _week(2, weekly_hours=55.0)]
    assert detect_week_flags(timeline, baseline)[2] == [WORKLOAD_ELEVATION]


def test_after_hours_and_hours_elevation_do_not_double_report():
    baseline = Baseline(after_hours_logins=1, weekly_hours=40.0)
    timeline = [
        _week(1, after_hours_logins=1, weekly_hours=40.0),
        _week(2, after_hours_logins=8, weekly_hours=55.0),
    ]
    assert detect_week_flags(timeline, baseline)[2].count(WORKLOAD_ELEVATION) == 1


def test_baseline_is_ignored_when_week_one_is_marked_missing():
    from src.domain import find_baseline

    assert find_baseline([_week(1, completed_tasks=5, data_missing=True)]) is None


# ---------------------------------------------------------------------------
# Consecutive-run confirmation
# ---------------------------------------------------------------------------
def test_confirm_consecutive_keeps_runs_and_drops_isolated_weeks():
    flags = {1: [], 2: ["A"], 3: ["A"], 4: [], 5: ["A"], 6: ["B"], 7: ["B"], 8: ["B"]}
    confirmed = confirm_consecutive(flags)
    assert confirmed["A"] == [2, 3]  # week 5 is isolated and excluded
    assert confirmed["B"] == [6, 7, 8]


def test_confirm_consecutive_on_empty_input():
    assert confirm_consecutive({}) == {}
    assert confirm_consecutive({1: [], 2: []}) == {}


def test_confirmed_signals_are_sorted_and_tagged():
    timeline = [
        _week(1, completed_tasks=20, weekly_hours=40.0),
        _week(2, completed_tasks=10, weekly_hours=25.0),
        _week(3, completed_tasks=9, weekly_hours=24.0),
    ]
    signals = confirm_signals(timeline)
    names = [s.signal_name for s in signals]
    assert names == sorted(names)
    assert all(not s.wellbeing_only for s in signals)

    wellbeing = confirm_signals(
        [
            _week(1, after_hours_logins=1),
            _week(2, after_hours_logins=6),
            _week(3, after_hours_logins=7),
        ]
    )
    assert [s.wellbeing_only for s in wellbeing] == [True]


# ---------------------------------------------------------------------------
# History records
# ---------------------------------------------------------------------------
def test_history_classification_matching_is_forgiving_of_formatting():
    assert HistoryRecord(score=2, classification="  healthy ").is_healthy is True
    assert HistoryRecord(score=7, classification="AT RISK").is_elevated is True
    assert HistoryRecord(score=5, classification="Watch").is_elevated is True
    assert HistoryRecord(score=9, classification="Silent Exit").is_elevated is True
    assert HistoryRecord(score=2, classification="Healthy").is_elevated is False
    assert HistoryRecord(score=2, classification="Nonsense").is_elevated is False


# ---------------------------------------------------------------------------
# Fakes and Protocols
# ---------------------------------------------------------------------------
def test_fakes_satisfy_their_protocols():
    assert isinstance(FakeRiskScorer(), RiskScorer)
    assert isinstance(FakeTrendEnricher(), TrendEnricher)


def test_fake_enricher_adds_prose_without_touching_the_evidence():
    original = Signal(
        signal_name=DECLINING_TASKS,
        weeks_detected=(2, 3),
        severity=Severity.HIGH,
    )
    enriched = FakeTrendEnricher().enrich("Priya", [original])[0]

    assert enriched.signal_name == original.signal_name
    assert enriched.weeks_detected == original.weeks_detected
    assert enriched.severity == original.severity
    assert "Priya" in enriched.details
    assert "2, 3" in enriched.details

    assert FakeTrendEnricher().enrich("Priya", []) == []


def test_fake_scorer_is_deterministic_and_bounded():
    scorer = FakeRiskScorer()
    signals = [
        Signal(
            signal_name=DECLINING_TASKS, weeks_detected=(2, 3), severity=Severity.HIGH
        )
    ]
    first = scorer.score("Priya", signals, 3, [])
    second = scorer.score("Priya", signals, 3, [])

    assert first == second
    assert MIN_SCORE <= first.score <= MAX_SCORE
    assert first.classification == classify(first.score)
    assert DECLINING_TASKS in first.rationale
    assert "Priya" in first.rationale


def test_fake_scorer_flags_insufficient_data_only_when_nothing_is_known():
    scorer = FakeRiskScorer()
    nothing = scorer.score("Ade", [], 1, [])
    assert nothing.insufficient_data is True
    assert nothing.score == MIN_SCORE
    assert "consecutive" in nothing.rationale

    with_history = scorer.score(
        "Ade", [], 3, [HistoryRecord(score=2, classification="Healthy")]
    )
    assert with_history.insufficient_data is False


def test_fake_scorer_ignores_wellbeing_signals_in_its_rationale():
    scorer = FakeRiskScorer()
    result = scorer.score(
        "Ade",
        [Signal(signal_name=WORKLOAD_ELEVATION, wellbeing_only=True)],
        2,
        [],
    )
    assert result.score == MIN_SCORE
    assert WORKLOAD_ELEVATION not in result.rationale
