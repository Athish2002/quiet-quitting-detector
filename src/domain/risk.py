# src/domain/risk.py
# Classification bands, recurrence bonus with decay, and a deterministic risk index.
#
# Extracted from risk_scorer_agent.py, which held the only copy of the bands and
# the decay rule.
#
# NOTE on `compute_risk_index`: this is the one genuinely NEW function here.
# §4 lists "risk index" as domain logic, but no deterministic scorer existed --
# today the LLM produces the score and the recurrence bonus is applied on top.
# This provides the deterministic baseline that §6.1 requires, and it is
# deliberately NOT yet wired into the agent path: Phase 1 is an extraction and
# must not change behaviour. Phase 6 promotes it over the LLM.

from __future__ import annotations

from src.domain.models import Classification, HistoryRecord, Severity, Signal

# Score bands. Kept as the single source of truth for both the agent path and
# any deterministic scorer.
WATCH_THRESHOLD = 4
AT_RISK_THRESHOLD = 6
SILENT_EXIT_THRESHOLD = 8

MIN_SCORE = 1
MAX_SCORE = 10

#: Consecutive Healthy weeks required to clear an accumulated recurrence bonus.
#: Recovery has to actually count for something, or the tool never lets anyone
#: back out of a flag once they have been in one.
HEALTHY_DECAY_WEEKS = 4

#: Prior elevated weeks needed before recurrence is applied.
RECURRENCE_MIN_ELEVATED_WEEKS = 2

_SEVERITY_WEIGHT: dict[Severity, float] = {
    Severity.LOW: 1.0,
    Severity.MEDIUM: 2.0,
    Severity.HIGH: 3.5,
}


def classify(score: int) -> str:
    """Map a numeric score to its band."""
    if score >= SILENT_EXIT_THRESHOLD:
        return Classification.SILENT_EXIT.value
    if score >= AT_RISK_THRESHOLD:
        return Classification.AT_RISK.value
    if score >= WATCH_THRESHOLD:
        return Classification.WATCH.value
    return Classification.HEALTHY.value


def clamp_score(score: float) -> int:
    """Constrain any score to the valid band. Never raises."""
    return max(MIN_SCORE, min(MAX_SCORE, round(score)))


def healthy_streak_from(history: list[HistoryRecord]) -> int:
    """Count consecutive Healthy weeks ending at the most recent record.

    `history` must be in chronological order.

    The stored `healthy_streak` on the LAST record is consulted once, as a floor:
    the lookback window (MAX_HISTORY_WEEKS) can truncate healthy weeks that really
    happened, and a recovery should not be forgotten just because it aged out.

    It is deliberately not consulted per-record. Doing so double-counted -- each
    older record's own counter was added on top of the run already walked, so two
    genuine healthy weeks reported three, and the bonus decayed after three weeks
    instead of the four HEALTHY_DECAY_WEEKS specifies. A decay rule that does not
    match its own documentation cannot be explained to the person it was applied
    to, which is the standard this system has to meet.
    """
    streak = 0
    for record in reversed(history):
        if not record.is_healthy:
            break
        streak += 1

    if streak and history:
        streak = max(streak, history[-1].healthy_streak)

    return streak


def compute_recurrence_bonus(history: list[HistoryRecord]) -> tuple[bool, int]:
    """Whether the +1 recurrence adjustment applies, and the current healthy streak.

    Applies when 2+ prior weeks were elevated AND the person has not since put
    together HEALTHY_DECAY_WEEKS consecutive Healthy weeks.

    Returns (apply_bonus, healthy_streak).
    """
    if not history:
        return False, 0

    streak = healthy_streak_from(history)
    if streak >= HEALTHY_DECAY_WEEKS:
        return False, streak

    elevated = sum(1 for record in history if record.is_elevated)
    return elevated >= RECURRENCE_MIN_ELEVATED_WEEKS, streak


def apply_recurrence_bonus(score: int, *, apply: bool) -> int:
    """Add the recurrence adjustment, capped at MAX_SCORE."""
    return clamp_score(score + 1) if apply else clamp_score(score)


def next_healthy_streak(classification: str, current_streak: int) -> int:
    """The streak carried into next week: incremented if Healthy, else reset."""
    is_healthy = classification.strip().casefold() == "healthy"
    return current_streak + 1 if is_healthy else 0


def compute_risk_index(
    signals: list[Signal],
    history: list[HistoryRecord] | None = None,
) -> int:
    """Deterministic risk score in [1, 10] from confirmed signals.

    NOT yet wired into the agent path -- see the module note. Provided so the
    system has an auditable, reproducible scorer that does not depend on an LLM,
    which §6.1 requires and which an LLM-produced number can never be.

    Properties it is designed to guarantee (and which are property-tested):
      * bounded: always within [1, 10]
      * monotonic: adding a signal, or raising one's severity, never LOWERS the
        score -- a tool where more evidence of struggle produces a calmer number
        is worse than no tool
      * wellbeing-only signals contribute NOTHING to risk; they exist to prompt
        a supportive check-in, never to count against someone
    """
    scoring_signals = [s for s in signals if not s.wellbeing_only]
    if not scoring_signals:
        return MIN_SCORE

    weight = sum(_SEVERITY_WEIGHT[s.severity] for s in scoring_signals)

    # Persistence matters as much as magnitude: a pattern held for many weeks is
    # more meaningful than a sharp two-week dip.
    persistence = sum(max(0, len(s.weeks_detected) - 1) for s in scoring_signals)

    raw = MIN_SCORE + weight + (0.5 * persistence)

    if history:
        apply, _ = compute_recurrence_bonus(history)
        raw = apply_recurrence_bonus(clamp_score(raw), apply=apply)

    return clamp_score(raw)
