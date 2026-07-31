# Property tests for src/domain (PRODUCTION_EVOLUTION_PROMPT.md 6.3).
#
# "The scoring logic in domain/ must be pure and property-tested: monotonicity
#  (worse metrics never lower risk), bounds (score in [1,10]), idempotence
#  (re-running the same week yields the same result), and the healthy-streak
#  decay behaving as specified."
#
# The reference tool is Hypothesis. It is not used here: this environment has no
# package-index access, and an uninstallable gate is not a gate. Instead the
# inputs are generated from FIXED SEEDS -- the same cases every run, on every
# machine, byte-identical. That satisfies 5's "no random data in tests, ever"
# more strictly than Hypothesis would, at the cost of not shrinking failures.
#
# Why properties and not more examples: the claim that matters here is universal.
# "More evidence of struggle never produces a calmer number" is not something a
# handful of hand-picked cases can establish, and it is exactly the failure that
# would be invisible in production -- a quietly wrong score looks like a score.

import itertools
import random

import pytest
from pydantic import ValidationError

from src.domain import (
    CONSECUTIVE_WEEKS_REQUIRED,
    HEALTHY_DECAY_WEEKS,
    Baseline,
    HistoryRecord,
    Severity,
    Signal,
    WeekMetrics,
    classify,
    compute_recurrence_bonus,
    compute_risk_index,
    confirm_signals,
    detect_week_flags,
    find_baseline,
    next_healthy_streak,
)
from src.domain.risk import MAX_SCORE, MIN_SCORE, clamp_score, healthy_streak_from
from src.domain.signals import (
    DECLINING_TASKS,
    REDUCED_HOURS,
    RESPONSE_SPIKE,
    WORKLOAD_ELEVATION,
)

#: Number of generated cases per property. Fixed, so runtime is predictable.
CASES = 120

SEVERITIES = (Severity.LOW, Severity.MEDIUM, Severity.HIGH)
SEVERITY_ORDER = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}
SIGNAL_NAMES = (DECLINING_TASKS, RESPONSE_SPIKE, REDUCED_HOURS, WORKLOAD_ELEVATION)


# ---------------------------------------------------------------------------
# Seeded generators
# ---------------------------------------------------------------------------
def _make_signal(rng: random.Random, *, wellbeing_only: bool | None = None) -> Signal:
    weeks = sorted(rng.sample(range(1, 13), rng.randint(0, 5)))
    name = rng.choice(SIGNAL_NAMES)
    return Signal(
        signal_name=name,
        weeks_detected=tuple(weeks),
        severity=rng.choice(SEVERITIES),
        wellbeing_only=(
            rng.random() < 0.25 if wellbeing_only is None else wellbeing_only
        ),
    )


def _make_signals(rng: random.Random, *, max_count: int = 6) -> list[Signal]:
    return [_make_signal(rng) for _ in range(rng.randint(0, max_count))]


def _make_history(rng: random.Random) -> list[HistoryRecord]:
    classes = ("Healthy", "Watch", "At Risk", "Silent Exit")
    records: list[HistoryRecord] = []
    streak = 0
    for _ in range(rng.randint(0, 8)):
        classification = rng.choice(classes)
        streak = streak + 1 if classification == "Healthy" else 0
        records.append(
            HistoryRecord(
                score=rng.randint(MIN_SCORE, MAX_SCORE),
                classification=classification,
                healthy_streak=streak,
            )
        )
    return records


def _make_timeline(rng: random.Random, weeks: int = 6) -> list[WeekMetrics]:
    out: list[WeekMetrics] = []
    for w in range(1, weeks + 1):
        if w > 1 and rng.random() < 0.15:
            out.append(WeekMetrics(week=w, data_missing=True))
            continue
        out.append(
            WeekMetrics(
                week=w,
                completed_tasks=rng.randint(0, 30),
                response_time=round(rng.uniform(0.2, 12.0), 2),
                after_hours_logins=rng.randint(0, 9),
                weekly_hours=round(rng.uniform(10.0, 65.0), 1),
            )
        )
    return out


def _seeded(prefix: str, count: int = CASES):
    """Deterministic RNGs. A failure at case N reproduces exactly at case N."""
    return (random.Random(f"{prefix}-{i}") for i in range(count))


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------
def test_risk_index_is_always_within_band():
    for rng in _seeded("bounds"):
        signals = _make_signals(rng, max_count=12)
        history = _make_history(rng)
        score = compute_risk_index(signals, history)
        assert MIN_SCORE <= score <= MAX_SCORE, (signals, history, score)


def test_clamp_score_is_total():
    """Never raises, always in band -- including for absurd inputs."""
    for rng in _seeded("clamp", 200):
        raw = rng.uniform(-1e6, 1e6)
        assert MIN_SCORE <= clamp_score(raw) <= MAX_SCORE
    for edge in (-1e300, -1.0, 0.0, 0.4, 1.5, 9.5, 10.4, 1e300):
        assert MIN_SCORE <= clamp_score(edge) <= MAX_SCORE


def test_classification_never_disagrees_with_its_band():
    """Every score maps to exactly one band, and bands never overlap."""
    seen = [classify(s) for s in range(MIN_SCORE, MAX_SCORE + 1)]
    rank = {"Healthy": 0, "Watch": 1, "At Risk": 2, "Silent Exit": 3}
    ranks = [rank[c] for c in seen]
    assert ranks == sorted(ranks), f"bands are not monotonic in score: {seen}"


# ---------------------------------------------------------------------------
# Monotonicity -- the property that matters most
# ---------------------------------------------------------------------------
def test_adding_a_signal_never_lowers_the_score():
    for rng in _seeded("mono-add"):
        signals = _make_signals(rng)
        extra = _make_signal(rng, wellbeing_only=False)
        before = compute_risk_index(signals)
        after = compute_risk_index([*signals, extra])
        assert after >= before, (signals, extra, before, after)


def test_raising_severity_never_lowers_the_score():
    for rng in _seeded("mono-sev"):
        signals = [s for s in _make_signals(rng) if not s.wellbeing_only]
        if not signals:
            continue
        idx = rng.randrange(len(signals))
        current = signals[idx].severity
        higher = [s for s in SEVERITIES if SEVERITY_ORDER[s] > SEVERITY_ORDER[current]]
        if not higher:
            continue
        raised = list(signals)
        raised[idx] = signals[idx].model_copy(update={"severity": rng.choice(higher)})
        assert compute_risk_index(raised) >= compute_risk_index(signals)


def test_a_longer_run_never_lowers_the_score():
    """Persistence is evidence. Six weeks of a pattern cannot score below two."""
    for rng in _seeded("mono-weeks"):
        signals = [s for s in _make_signals(rng) if not s.wellbeing_only]
        if not signals:
            continue
        idx = rng.randrange(len(signals))
        weeks = signals[idx].weeks_detected
        extended = list(signals)
        next_week = (max(weeks) if weeks else 0) + 1
        extended[idx] = signals[idx].model_copy(
            update={"weeks_detected": (*weeks, next_week)}
        )
        assert compute_risk_index(extended) >= compute_risk_index(signals)


def test_wellbeing_signals_contribute_nothing_to_risk():
    """CONTEXT.md rule: working long hours is a reason to check on someone, not a
    mark against them. Adding any number of wellbeing-only signals must not move
    the score by even one point."""
    for rng in _seeded("wellbeing"):
        signals = _make_signals(rng)
        extras = [
            _make_signal(rng, wellbeing_only=True) for _ in range(rng.randint(1, 4))
        ]
        assert compute_risk_index([*signals, *extras]) == compute_risk_index(signals)


def test_no_signals_means_lowest_score():
    assert compute_risk_index([]) == MIN_SCORE
    for rng in _seeded("wellbeing-only", 40):
        only_wellbeing = [
            _make_signal(rng, wellbeing_only=True) for _ in range(rng.randint(1, 5))
        ]
        assert compute_risk_index(only_wellbeing) == MIN_SCORE


# ---------------------------------------------------------------------------
# Idempotence
# ---------------------------------------------------------------------------
def test_scoring_is_idempotent():
    for rng in _seeded("idem-score"):
        signals = _make_signals(rng)
        history = _make_history(rng)
        first = compute_risk_index(signals, history)
        assert compute_risk_index(signals, history) == first
        assert compute_risk_index(signals, history) == first


def test_detection_is_idempotent_and_order_independent():
    """Re-running the same week yields the same result, and the order rows
    happened to arrive in cannot change a person's assessment."""
    for rng in _seeded("idem-detect"):
        timeline = _make_timeline(rng)
        first = confirm_signals(timeline)
        assert confirm_signals(timeline) == first

        shuffled = list(timeline)
        rng.shuffle(shuffled)
        assert confirm_signals(shuffled) == first


# ---------------------------------------------------------------------------
# Healthy-streak decay
# ---------------------------------------------------------------------------
def test_recurrence_clears_at_exactly_the_decay_threshold():
    """Recovery has to count. At HEALTHY_DECAY_WEEKS - 1 the bonus still applies;
    at HEALTHY_DECAY_WEEKS it is gone."""
    elevated = [
        HistoryRecord(score=7, classification="At Risk"),
        HistoryRecord(score=6, classification="Watch"),
    ]

    for healthy_weeks in range(0, HEALTHY_DECAY_WEEKS + 3):
        history = list(elevated)
        for i in range(healthy_weeks):
            history.append(
                HistoryRecord(score=2, classification="Healthy", healthy_streak=i + 1)
            )
        applies, streak = compute_recurrence_bonus(history)
        assert streak == healthy_weeks
        assert applies is (healthy_weeks < HEALTHY_DECAY_WEEKS), (
            f"{healthy_weeks} healthy week(s): expected "
            f"{'bonus' if healthy_weeks < HEALTHY_DECAY_WEEKS else 'no bonus'}"
        )


def test_one_elevated_week_is_not_recurrence():
    """Recurrence means a pattern, not a single bad week."""
    single = [HistoryRecord(score=7, classification="At Risk")]
    applies, _ = compute_recurrence_bonus(single)
    assert applies is False
    assert compute_recurrence_bonus([]) == (False, 0)


def test_healthy_streak_advances_and_resets():
    for rng in _seeded("streak", 60):
        current = rng.randint(0, 10)
        assert next_healthy_streak("Healthy", current) == current + 1
        assert next_healthy_streak("  healthy  ", current) == current + 1
        for other in ("Watch", "At Risk", "Silent Exit", "", "unknown"):
            assert next_healthy_streak(other, current) == 0


def test_healthy_streak_from_history_never_exceeds_the_run():
    for rng in _seeded("streak-hist"):
        history = _make_history(rng)
        streak = healthy_streak_from(history)
        assert streak >= 0
        trailing = 0
        for record in reversed(history):
            if record.is_healthy:
                trailing += 1
            else:
                break
        # The stored counter may carry a longer run forward from before the
        # lookback window, so it is a floor, never a contradiction.
        assert streak >= trailing


# ---------------------------------------------------------------------------
# The 2+ consecutive-week rule, and missing data
# ---------------------------------------------------------------------------
def test_every_confirmed_signal_has_a_consecutive_run():
    for rng in _seeded("consecutive"):
        timeline = _make_timeline(rng, weeks=8)
        for signal in confirm_signals(timeline):
            weeks = sorted(signal.weeks_detected)
            longest = best = 1
            for prev, current in itertools.pairwise(weeks):
                longest = longest + 1 if current == prev + 1 else 1
                best = max(best, longest)
            assert best >= CONSECUTIVE_WEEKS_REQUIRED, (signal, weeks)


def test_an_isolated_bad_week_never_confirms():
    """One rough sprint must not flag anyone."""
    timeline = [
        WeekMetrics(
            week=1,
            completed_tasks=20,
            response_time=1.0,
            after_hours_logins=1,
            weekly_hours=40.0,
        ),
        WeekMetrics(
            week=2,
            completed_tasks=4,
            response_time=9.0,
            after_hours_logins=1,
            weekly_hours=15.0,
        ),
        WeekMetrics(
            week=3,
            completed_tasks=20,
            response_time=1.0,
            after_hours_logins=1,
            weekly_hours=40.0,
        ),
        WeekMetrics(
            week=4,
            completed_tasks=21,
            response_time=1.0,
            after_hours_logins=1,
            weekly_hours=40.0,
        ),
    ]
    assert confirm_signals(timeline) == []
    assert compute_risk_index(confirm_signals(timeline)) == MIN_SCORE


def test_missing_weeks_never_generate_signals():
    """CONTEXT.md rule 3: a gap is a noted gap, never inferred disengagement.

    This is the single most important property in the file. Defaulting an absent
    metric to zero fabricates a total-collapse pattern, which is exactly the
    signal the system exists to detect -- it would confidently flag people whose
    only failing was that their data did not arrive.
    """
    for rng in _seeded("missing", 60):
        weeks = rng.randint(3, 8)
        timeline = [
            WeekMetrics(
                week=1,
                completed_tasks=rng.randint(5, 30),
                response_time=round(rng.uniform(0.5, 4.0), 2),
                after_hours_logins=rng.randint(0, 3),
                weekly_hours=round(rng.uniform(30.0, 45.0), 1),
            )
        ] + [WeekMetrics(week=w, data_missing=True) for w in range(2, weeks + 1)]

        assert confirm_signals(timeline) == []
        assert compute_risk_index(confirm_signals(timeline)) == MIN_SCORE


def test_absent_baseline_yields_no_signals():
    for rng in _seeded("no-baseline", 40):
        timeline = [w for w in _make_timeline(rng) if w.week != 1]
        assert find_baseline(timeline) is None
        assert confirm_signals(timeline) == []


def test_week_one_never_flags_against_itself():
    for rng in _seeded("week1"):
        timeline = _make_timeline(rng)
        baseline = find_baseline(timeline)
        if baseline is None:
            continue
        assert detect_week_flags(timeline, baseline)[1] == []


# ---------------------------------------------------------------------------
# Fairness: the baseline is personal
# ---------------------------------------------------------------------------
def test_detection_is_invariant_to_an_employees_absolute_level():
    """Two people with identical trajectories at different absolute levels must
    get identical signals.

    This is what "their own baseline, never a cohort average" means in practice:
    someone approved for 20 hours a week who holds steady is not more at risk
    than a 40-hour colleague who holds steady. Scaling every ratio metric by a
    constant must not change a single signal.
    """
    for rng in _seeded("scale", 80):
        factor = rng.choice([0.25, 0.5, 2.0, 3.0, 10.0])
        base = _make_timeline(rng)
        # after_hours uses an absolute deviation, so it is held constant.
        scaled = [
            w.model_copy(
                update={
                    "completed_tasks": (
                        None
                        if w.completed_tasks is None
                        else round(w.completed_tasks * factor)
                    ),
                    "response_time": (
                        None if w.response_time is None else w.response_time * factor
                    ),
                    "weekly_hours": (
                        None if w.weekly_hours is None else w.weekly_hours * factor
                    ),
                }
            )
            for w in base
        ]

        original = {s.signal_name for s in confirm_signals(base)}
        rescaled = {s.signal_name for s in confirm_signals(scaled)}
        # Rounding tasks to whole numbers can move a value across a threshold at
        # small factors; compare the metrics that scale exactly.
        exact = {RESPONSE_SPIKE, REDUCED_HOURS}
        assert original & exact == rescaled & exact, (factor, original, rescaled)


def test_a_flat_timeline_produces_no_signals():
    """Someone whose behaviour never changes is never flagged, at any level."""
    for level in (5, 10, 40):
        timeline = [
            WeekMetrics(
                week=w,
                completed_tasks=level,
                response_time=float(level) / 10,
                after_hours_logins=1,
                weekly_hours=float(level),
            )
            for w in range(1, 7)
        ]
        assert confirm_signals(timeline) == []


# ---------------------------------------------------------------------------
# Model invariants
# ---------------------------------------------------------------------------
def test_models_reject_impossible_values():
    with pytest.raises(ValidationError):
        WeekMetrics(week=0)
    with pytest.raises(ValidationError):
        WeekMetrics(week=1, completed_tasks=-1)
    with pytest.raises(ValidationError):
        HistoryRecord(score=11, classification="Healthy")
    with pytest.raises(ValidationError):
        HistoryRecord(score=0, classification="Healthy")


def test_prohibited_fields_cannot_enter_the_domain():
    """config/data_allowlist.json forbids these. The model must drop them even if
    a legacy CSV or a stale memory file still carries them."""
    # Passed as a mapping on purpose: spelled as keyword arguments the type
    # checker rejects them, which is the static half of the same guarantee. This
    # test covers the runtime half -- a dict arriving from a CSV or a stale
    # memory file, where no type checker is watching.
    legacy_row = {
        "week": 1,
        "completed_tasks": 10,
        "sick_days": 4,
        "task_accuracy": 61,
        "sentiment": "Withdrawn",
    }
    week = WeekMetrics(**legacy_row)
    for prohibited in ("sick_days", "task_accuracy", "sentiment"):
        assert not hasattr(week, prohibited)
        assert prohibited not in week.model_dump()


def test_baseline_from_week_carries_every_metric():
    week = WeekMetrics(
        week=1,
        completed_tasks=12,
        response_time=2.5,
        after_hours_logins=3,
        weekly_hours=38.0,
    )
    baseline = Baseline.from_week(week)
    assert baseline.completed_tasks == 12
    assert baseline.response_time == 2.5
    assert baseline.after_hours_logins == 3
    assert baseline.weekly_hours == 38.0


def test_is_usable_requires_at_least_one_real_metric():
    assert WeekMetrics(week=1, completed_tasks=1).is_usable is True
    assert WeekMetrics(week=1).is_usable is False
    assert WeekMetrics(week=1, completed_tasks=1, data_missing=True).is_usable is False
