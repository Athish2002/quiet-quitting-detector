# src/domain/signals.py
# Signal detection: personal-baseline deviation + consecutive-week confirmation.
#
# Extracted verbatim in behaviour from trend_detector_agent.py, which held the
# only copy. Pure: takes weeks, returns signals. No I/O, no LLM.
#
# Two invariants this file exists to protect:
#   1. Every comparison is against the individual's OWN baseline. Never a team
#      or cohort average -- that is what makes such a tool unfair to people on
#      different schedules, timezones, or working patterns.
#   2. A single bad week is never a signal. Confirmation requires 2+ CONSECUTIVE
#      weeks, so one rough sprint cannot flag someone.

from __future__ import annotations

from src.domain.changepoint import (
    CUSUM_SLACK,
    concerning_deviation,
    cusum_shift_week,
    is_sustained,
    longest_consecutive_run,
)
from src.domain.cohort import is_shared_confound, remove_shared_confound
from src.domain.models import (
    Baseline,
    MetricBaseline,
    Severity,
    Signal,
    WeekMetrics,
)
from src.domain.statistics import (
    Direction,
    build_baseline,
    effect_size,
    is_significant,
    relative_change,
)

# Deviation thresholds, all expressed relative to the person's own baseline.
# Absolute cut-offs were removed in Phase 0: they compared people to a
# population norm and flagged approved part-time schedules, phased returns from
# leave, and non-US timezones as disengagement.
TASK_DROP_PCT_MEDIUM = 0.20
TASK_DROP_PCT_HIGH = 0.40
RESPONSE_TIME_PCT = 0.50
AFTER_HOURS_DEVIATION = 2
HOURS_DEVIATION_PCT = 0.25

#: A pattern must persist this many consecutive weeks to count.
CONSECUTIVE_WEEKS_REQUIRED = 2

DECLINING_TASKS = "Declining Task Completion"
RESPONSE_SPIKE = "Response Time Spike"
WORKLOAD_ELEVATION = "Sustained Workload Elevation"
REDUCED_HOURS = "Reduced Working Hours"

#: Signals that may prompt a supportive check-in but must NEVER raise risk.
#: after-hours activity correlates with timezone and caregiving, not disengagement.
WELLBEING_ONLY_SIGNALS = frozenset({WORKLOAD_ELEVATION})


def find_baseline(timeline: list[WeekMetrics]) -> Baseline | None:
    """The week-1 record, or None when it is missing.

    Returning None matters: without a baseline there is nothing to deviate
    from, and the caller must report a gap rather than infer disengagement
    (CONTEXT.md rule 3).
    """
    for week in timeline:
        if week.week == 1 and not week.data_missing:
            return Baseline.from_week(week)
    return None


def detect_week_flags(
    timeline: list[WeekMetrics], baseline: Baseline
) -> dict[int, list[str]]:
    """Map each week to the signal names active that week.

    Week 1 is the baseline and never flags against itself. A week with missing
    data yields no flags -- a gap is not evidence.
    """
    flags_by_week: dict[int, list[str]] = {}

    for week in timeline:
        if week.data_missing or week.week == 1:
            flags_by_week[week.week] = []
            continue

        flags: list[str] = []

        if (
            week.completed_tasks is not None
            and baseline.completed_tasks
            and baseline.completed_tasks > 0
        ):
            drop = (
                baseline.completed_tasks - week.completed_tasks
            ) / baseline.completed_tasks
            if drop >= TASK_DROP_PCT_MEDIUM:
                flags.append(DECLINING_TASKS)

        if (
            week.response_time is not None
            and baseline.response_time
            and baseline.response_time > 0
        ):
            increase = (
                week.response_time - baseline.response_time
            ) / baseline.response_time
            if increase > RESPONSE_TIME_PCT:
                flags.append(RESPONSE_SPIKE)

        if (
            week.after_hours_logins is not None
            and baseline.after_hours_logins is not None
            and week.after_hours_logins
            > baseline.after_hours_logins + AFTER_HOURS_DEVIATION
        ):
            flags.append(WORKLOAD_ELEVATION)

        if week.weekly_hours is not None and baseline.weekly_hours:
            delta = (week.weekly_hours - baseline.weekly_hours) / baseline.weekly_hours
            if delta <= -HOURS_DEVIATION_PCT:
                flags.append(REDUCED_HOURS)
            elif delta >= HOURS_DEVIATION_PCT and WORKLOAD_ELEVATION not in flags:
                flags.append(WORKLOAD_ELEVATION)

        flags_by_week[week.week] = flags

    return flags_by_week


def confirm_consecutive(flags_by_week: dict[int, list[str]]) -> dict[str, list[int]]:
    """Keep only signals appearing in >= CONSECUTIVE_WEEKS_REQUIRED consecutive weeks."""
    names: set[str] = set()
    for flags in flags_by_week.values():
        names.update(flags)

    confirmed: dict[str, list[int]] = {}
    for name in names:
        active = sorted(w for w, flags in flags_by_week.items() if name in flags)

        runs: list[int] = []
        i = 0
        while i < len(active):
            run = [active[i]]
            j = i + 1
            while j < len(active) and active[j] == active[j - 1] + 1:
                run.append(active[j])
                j += 1
            if len(run) >= CONSECUTIVE_WEEKS_REQUIRED:
                runs.extend(run)
            i = j

        if runs:
            confirmed[name] = sorted(set(runs))

    return confirmed


def assign_severity(
    signal_name: str,
    weeks_detected: list[int],
    timeline: list[WeekMetrics],
    baseline: Baseline,
) -> Severity:
    """Grade a confirmed signal by the magnitude of its worst week."""
    detected = set(weeks_detected)
    weeks = [w for w in timeline if w.week in detected and not w.data_missing]

    if signal_name == DECLINING_TASKS and baseline.completed_tasks:
        worst = 0.0
        for week in weeks:
            if week.completed_tasks is not None:
                worst = max(
                    worst,
                    (baseline.completed_tasks - week.completed_tasks)
                    / baseline.completed_tasks,
                )
        if worst >= TASK_DROP_PCT_HIGH:
            return Severity.HIGH
        return Severity.MEDIUM if worst >= TASK_DROP_PCT_MEDIUM else Severity.LOW

    if signal_name == RESPONSE_SPIKE and baseline.response_time:
        worst = 0.0
        for week in weeks:
            if week.response_time is not None:
                worst = max(
                    worst,
                    (week.response_time - baseline.response_time)
                    / baseline.response_time,
                )
        if worst >= 1.0:
            return Severity.HIGH
        return Severity.MEDIUM if worst >= RESPONSE_TIME_PCT else Severity.LOW

    if signal_name == REDUCED_HOURS and baseline.weekly_hours:
        observed = [w.weekly_hours for w in weeks if w.weekly_hours is not None]
        if observed:
            drop = (baseline.weekly_hours - min(observed)) / baseline.weekly_hours
            if drop >= 0.50:
                return Severity.HIGH
            return Severity.MEDIUM if drop >= HOURS_DEVIATION_PCT else Severity.LOW

    if signal_name == WORKLOAD_ELEVATION:
        # Capped at medium by design. This is a wellbeing prompt; letting it
        # escalate is how "works long hours" becomes a mark against someone
        # instead of a reason to check on them.
        return Severity.MEDIUM

    return Severity.MEDIUM


def confirm_signals_threshold(timeline: list[WeekMetrics]) -> list[Signal]:
    """Phase 1's detection: fixed percentage cut-offs against the week-1 point.

    Superseded by `confirm_signals` in Phase 2 and kept deliberately, for two
    reasons. It is the "before" side of docs/PHASE2_BEFORE_AFTER.md, so the claim
    that the new method rejects noise the old one flagged is demonstrated on real
    output rather than asserted. And it stays runnable, so the comparison can be
    re-run against any future fixture instead of being a one-off screenshot.

    Not called by any production path.
    """
    baseline = find_baseline(timeline)
    if baseline is None:
        return []

    confirmed = confirm_consecutive(detect_week_flags(timeline, baseline))

    return [
        Signal(
            signal_name=name,
            weeks_detected=tuple(weeks),
            severity=assign_severity(name, weeks, timeline, baseline),
            wellbeing_only=name in WELLBEING_ONLY_SIGNALS,
        )
        for name, weeks in sorted(confirmed.items())
    ]


# ---------------------------------------------------------------------------
# Phase 2 -- distributional baselines, change-point confirmation
# ---------------------------------------------------------------------------

#: Which direction of movement is the concerning one, per metric. Getting this
#: wrong in either direction is a real harm: treating rising hours as risk
#: penalises people for overwork, and treating falling response time as risk
#: penalises people for getting faster.
METRIC_DIRECTION: dict[str, Direction] = {
    "completed_tasks": Direction.BELOW,
    "response_time": Direction.ABOVE,
    "weekly_hours": Direction.BELOW,
    "after_hours_logins": Direction.ABOVE,
}

METRIC_SIGNAL: dict[str, str] = {
    "completed_tasks": DECLINING_TASKS,
    "response_time": RESPONSE_SPIKE,
    "weekly_hours": REDUCED_HOURS,
    "after_hours_logins": WORKLOAD_ELEVATION,
}

#: Materiality floor per metric -- how big a proportional move has to be before
#: it is worth a manager's attention at all, regardless of how statistically
#: unusual it is for the person. Without this, someone with an extremely steady
#: history gets flagged for a rounding error.
METRIC_MATERIALITY: dict[str, float] = {
    "completed_tasks": TASK_DROP_PCT_MEDIUM,
    "response_time": RESPONSE_TIME_PCT,
    "weekly_hours": HOURS_DEVIATION_PCT,
    "after_hours_logins": 0.5,
}

#: Most weeks that may form the reference window. Anchoring on the EARLIEST
#: weeks rather than a rolling window is deliberate: a rolling median follows a
#: gradual decline downward, so a person sliding steadily for two months would
#: look normal at every single step. The thing the tool most needs to see is
#: exactly the thing a rolling baseline hides.
BASELINE_MAX_WEEKS = 3

#: Effect-size cut-offs for grading a confirmed signal, in units of the person's
#: own variability.
SEVERITY_EFFECT_HIGH = 4.0
SEVERITY_EFFECT_MEDIUM = 2.0


def _usable(timeline: list[WeekMetrics]) -> list[WeekMetrics]:
    return sorted((w for w in timeline if w.is_usable), key=lambda w: w.week)


def _metric_series(weeks: list[WeekMetrics], metric: str) -> list[tuple[int, float]]:
    out: list[tuple[int, float]] = []
    for week in weeks:
        value = getattr(week, metric, None)
        if value is not None:
            out.append((week.week, float(value)))
    return out


def baseline_window_size(observation_count: int) -> int:
    """How many of the earliest weeks form the reference window.

    Half the available history, capped at BASELINE_MAX_WEEKS and never below one.
    Half rather than all of it because the remainder has to be left to evaluate:
    a baseline built from every week includes the very decline being looked for,
    and averages it away.
    """
    return max(1, min(BASELINE_MAX_WEEKS, observation_count // 2))


def build_personal_baselines(
    timeline: list[WeekMetrics],
) -> dict[str, MetricBaseline]:
    """A distributional baseline per metric, from this person's own early weeks.

    Never a cohort or team figure. See src/domain/cohort.py for the only use of
    other people's data this system permits.
    """
    weeks = _usable(timeline)
    baselines: dict[str, MetricBaseline] = {}

    for metric in METRIC_DIRECTION:
        series = _metric_series(weeks, metric)
        if not series:
            continue
        window = baseline_window_size(len(series))
        baseline = build_baseline([value for _, value in series[:window]])
        if baseline is not None:
            baselines[metric] = baseline

    return baselines


def _concerning_weeks(
    series: list[tuple[int, float]],
    baseline: MetricBaseline,
    direction: Direction,
    from_week: int,
    materiality: float,
) -> tuple[int, ...]:
    """Weeks at or after `from_week` sitting materially on the concerning side.

    A week has to clear both bars -- unusual for this person, and large enough
    to matter -- exactly as `is_significant` requires. Someone with an extremely
    steady history can have a 5% move register as two units of their own spread;
    listing that week as evidence pads the case with a week that contributed
    nothing, and a manager reading "weeks 3, 4, 5, 6" reasonably concludes this
    started a week earlier than it did.
    """
    weeks: list[int] = []
    for week, value in series:
        if week < from_week:
            continue
        deviation = concerning_deviation(
            value, baseline, downward=direction is Direction.BELOW
        )
        change = relative_change(value, baseline)
        material = (
            change <= -materiality
            if direction is Direction.BELOW
            else change >= materiality
        )
        if deviation > CUSUM_SLACK and material:
            weeks.append(week)
    return tuple(weeks)


def detect_metric_signal(
    metric: str,
    timeline: list[WeekMetrics],
    baseline: MetricBaseline,
    *,
    cohort_shifts: dict[int, float] | None = None,
) -> Signal | None:
    """Confirm or reject one metric's pattern for one person.

    A pattern is confirmed when it clears all three of:

      1. the 2+-consecutive-week floor, which is kept exactly as it was -- the
         floor was never the problem, only the belief that it was sufficient;
      2. a sustained level shift found by CUSUM, or a week that is significantly
         unusual for this person on both effect size and materiality;
      3. survival of the cohort correction -- a drop everyone shared in the same
         week is not evidence about any individual.

    Returns None when the pattern fails any of them, which is the common and
    correct outcome. Most weeks are just weeks.
    """
    direction = METRIC_DIRECTION[metric]
    weeks = _usable(timeline)
    series = _metric_series(weeks, metric)
    if len(series) < CONSECUTIVE_WEEKS_REQUIRED:
        return None

    # (3) Strip out movement the whole cohort shared before judging anyone.
    corrected: list[tuple[int, float]] = []
    for week, value in series:
        shift = (cohort_shifts or {}).get(week)
        if is_shared_confound(shift):
            corrected.append(
                (week, remove_shared_confound(value, baseline.centre, shift))
            )
        else:
            corrected.append((week, value))

    # (2a) A sustained regime shift.
    shift_week = cusum_shift_week(
        corrected, baseline, downward=direction is Direction.BELOW
    )

    # (2b) Or an individually significant week, on both tests.
    materiality = METRIC_MATERIALITY[metric]
    significant_weeks = tuple(
        week
        for week, value in corrected
        if is_significant(
            value,
            baseline,
            direction=direction,
            minimum_relative_change=materiality,
        )
    )

    if shift_week is not None:
        detected = _concerning_weeks(
            corrected, baseline, direction, shift_week, materiality
        )
    elif significant_weeks:
        detected = _concerning_weeks(
            corrected, baseline, direction, min(significant_weeks), materiality
        )
    else:
        return None

    # (1) The floor. Unchanged, and still the last word.
    if longest_consecutive_run(detected) < CONSECUTIVE_WEEKS_REQUIRED:
        return None

    # (4) And it has to still be happening. A pattern that ended two weeks ago
    # has resolved, and reporting it as CURRENT risk is how a tool turns
    # somebody's worst month into a permanent mark on them. The history and
    # recurrence machinery already carries forward the fact that it happened;
    # this week's assessment should describe this week.
    if not is_sustained(detected, max(week for week, _ in corrected)):
        return None

    peak = max(
        (
            effect_size(value, baseline, direction=direction)
            for week, value in corrected
            if week in detected
        ),
        default=0.0,
    )

    name = METRIC_SIGNAL[metric]
    return Signal(
        signal_name=name,
        weeks_detected=detected,
        severity=grade_effect(name, peak),
        wellbeing_only=name in WELLBEING_ONLY_SIGNALS,
    )


def grade_effect(signal_name: str, peak_effect: float) -> Severity:
    """Grade a confirmed signal by how far outside normal its worst week ran."""
    if signal_name in WELLBEING_ONLY_SIGNALS:
        # Capped at medium by design. This is a wellbeing prompt; letting it
        # escalate is how "works long hours" becomes a mark against someone
        # instead of a reason to check on them.
        return Severity.MEDIUM
    if peak_effect >= SEVERITY_EFFECT_HIGH:
        return Severity.HIGH
    if peak_effect >= SEVERITY_EFFECT_MEDIUM:
        return Severity.MEDIUM
    return Severity.LOW


def confirm_signals(
    timeline: list[WeekMetrics],
    cohort_shifts: dict[str, dict[int, float]] | None = None,
) -> list[Signal]:
    """Full detection pass against the person's own distribution.

    Returns [] when there is no usable week-1 baseline, which the caller must
    surface as a data gap rather than as "no problems found".

    `cohort_shifts` is optional and maps metric -> week -> the proportional move
    everybody saw that week. It can only ever REMOVE signals, never add one.
    """
    if find_baseline(timeline) is None:
        return []

    baselines = build_personal_baselines(timeline)

    signals: list[Signal] = []
    for metric in sorted(baselines):
        signal = detect_metric_signal(
            metric,
            timeline,
            baselines[metric],
            cohort_shifts=(cohort_shifts or {}).get(metric),
        )
        if signal is not None:
            signals.append(signal)

    return sorted(signals, key=lambda s: s.signal_name)
