# src/domain/uncertainty.py
# Making "we are not sure yet" a first-class answer (spec 6.1).
#
# "Every score carries a confidence interval and an explicit insufficient_data
#  state. Low confidence must visibly suppress the strength of the briefing --
#  the manager sees 'we're not sure yet,' not a confident number built on three
#  data points."
#
# The failure this prevents is specific and common: a system with two weeks of
# patchy data prints "6/10 -- At Risk", the manager reads a number, and the
# number carries authority the evidence never had. Nobody lied; the interface
# simply had no way to say "this is a guess". So it is said here, structurally,
# in a field the caller cannot forget to check.
#
# An honest note on what `score_range` is
# ---------------------------------------
# It is a heuristic band that widens as evidence thins. It is NOT a frequentist
# confidence interval and does not carry a coverage guarantee -- there is no
# sampling distribution here to derive one from, and inventing one would dress a
# rule of thumb in borrowed statistical authority. That is precisely the move
# this project must not make, so the field is named `score_range` rather than
# `confidence_interval`, and the limitation is written down in
# docs/LIMITATIONS.md rather than left for a reader to discover.

from __future__ import annotations

from src.domain.models import Confidence, WeekMetrics
from src.domain.risk import MAX_SCORE, MIN_SCORE
from src.domain.signals import BASELINE_MAX_WEEKS, baseline_window_size

#: Weeks of usable history needed before the evidence can be called strong.
HIGH_CONFIDENCE_WEEKS = 6
MODERATE_CONFIDENCE_WEEKS = 4
LOW_CONFIDENCE_WEEKS = 2

#: Above this fraction of missing weeks, confidence is capped no matter how long
#: the timeline is. Ten weeks of history with six missing is not six weeks of
#: evidence, it is four weeks of evidence and an unanswered question.
MISSING_FRACTION_CAP = 0.34


def assess_confidence(
    *,
    usable_weeks: int,
    total_weeks: int,
    has_distributional_baseline: bool,
) -> Confidence:
    """How much weight this assessment can bear.

    Deliberately pessimistic at the boundaries. Over-stating confidence puts a
    number in front of a manager that the data cannot support; under-stating it
    prompts a conversation instead. Only one of those two errors can cost
    somebody their standing at work.
    """
    if usable_weeks <= 0:
        return Confidence.NONE
    if usable_weeks < LOW_CONFIDENCE_WEEKS:
        return Confidence.LOW

    missing = max(0, total_weeks - usable_weeks)
    missing_fraction = missing / total_weeks if total_weeks else 0.0

    if missing_fraction > MISSING_FRACTION_CAP:
        return Confidence.LOW

    if not has_distributional_baseline:
        # A point baseline is still a baseline, but it cannot tell ordinary
        # variation from a real change, so it never earns better than moderate.
        return (
            Confidence.LOW
            if usable_weeks < MODERATE_CONFIDENCE_WEEKS
            else (Confidence.MODERATE)
        )

    if usable_weeks >= HIGH_CONFIDENCE_WEEKS:
        return Confidence.HIGH
    if usable_weeks >= MODERATE_CONFIDENCE_WEEKS:
        return Confidence.MODERATE
    return Confidence.LOW


#: How wide the plausible band is at each confidence level, in score points.
_BAND_WIDTH = {
    Confidence.NONE: 4,
    Confidence.LOW: 3,
    Confidence.MODERATE: 2,
    Confidence.HIGH: 1,
}


def score_range(score: int, confidence: Confidence) -> tuple[int, int]:
    """The band the score plausibly sits in, clamped to the valid scale.

    Wider when there is less to go on. A five-point-wide band on a ten-point
    scale is the system saying, legibly, that it does not know -- which is more
    useful than a precise-looking single number that is equally uninformed.
    """
    width = _BAND_WIDTH[confidence]
    return (max(MIN_SCORE, score - width), min(MAX_SCORE, score + width))


def assess_from_timeline(timeline: list[WeekMetrics]) -> Confidence:
    """Confidence for a whole employee timeline, counting gaps honestly.

    A week marked `data_missing`, or one carrying no metric at all, is counted as
    total-but-not-usable. That is the entire point: ten weeks on file with six
    absent is not ten weeks of evidence, and the arithmetic must not let it look
    like it.
    """
    if not timeline:
        return Confidence.NONE

    usable = [week for week in timeline if week.is_usable]
    return assess_confidence(
        usable_weeks=len(usable),
        total_weeks=len(timeline),
        has_distributional_baseline=(
            baseline_window_size(len(usable)) >= min(BASELINE_MAX_WEEKS, 3)
            and len(usable) >= 2 * BASELINE_MAX_WEEKS
        ),
    )


def suppresses_briefing(confidence: Confidence) -> bool:
    """Whether the briefing must be softened rather than stated as fact.

    Consumers use this to change the language, not to hide the finding: the
    manager still hears that something was noticed, framed as a question worth
    asking rather than a conclusion already reached.
    """
    return confidence in (Confidence.NONE, Confidence.LOW)
