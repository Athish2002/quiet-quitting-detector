# src/domain/threshold_signals.py
# Phase 1's detection method: fixed percentage cut-offs against the week-1 point.
#
# SUPERSEDED by src/domain/signals.py in Phase 2 and kept deliberately, for two
# reasons. It is the "before" side of docs/PHASE2_BEFORE_AFTER.md, so the claim
# that the new method rejects noise the old one flagged is demonstrated on real
# output rather than asserted. And it stays runnable, so that comparison can be
# re-run against any future fixture instead of being a one-off screenshot.
#
# Not called by any production path. Split out of signals.py so the module that
# IS called holds only the method that is actually in use -- two detection
# methods in one file is an invitation to call the wrong one.

from __future__ import annotations

from src.domain.models import Baseline, Severity, Signal, WeekMetrics
from src.domain.signals import (
    AFTER_HOURS_DEVIATION,
    CONSECUTIVE_WEEKS_REQUIRED,
    DECLINING_TASKS,
    HOURS_DEVIATION_PCT,
    REDUCED_HOURS,
    RESPONSE_SPIKE,
    RESPONSE_TIME_PCT,
    TASK_DROP_PCT_HIGH,
    TASK_DROP_PCT_MEDIUM,
    WELLBEING_ONLY_SIGNALS,
    WORKLOAD_ELEVATION,
    find_baseline,
)


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
