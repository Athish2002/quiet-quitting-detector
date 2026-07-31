# src/domain/attribution.py
# Why the score is what it is (spec 6.1, counterfactual/attribution layer).
#
# "For each flagged employee, produce the ranked contribution of each metric to
#  the score, so the briefing can say *why* -- and so a wrong call can be
#  debugged."
#
# Two independent reasons this is not optional.
#
# For the person: an unexplained score is an accusation with no evidence
# attached. If someone is told a system flagged them, "your response times rose
# well beyond your own normal in weeks 4 and 5" is something they can confirm,
# correct, or explain. "The model said 7" is something they can only submit to.
#
# For the system: without attribution, a wrong call is undebuggable. There is no
# way to find out that the tool has been quietly flagging everyone who switched
# to a compressed four-day week, because nothing records which metric drove it.
#
# Contributions are derived from the SAME weights the score uses, so they cannot
# drift into a plausible-sounding story told after the fact about a number
# arrived at some other way.

from __future__ import annotations

from src.domain.models import Attribution, Signal
from src.domain.risk import signal_contribution

#: Which observable metric each signal is a statement about. Used to make the
#: explanation concrete: managers act on "response times", not on the internal
#: name of a detector.
SIGNAL_METRIC = {
    "Declining Task Completion": "completed_tasks",
    "Response Time Spike": "response_time",
    "Reduced Working Hours": "weekly_hours",
    "Sustained Workload Elevation": "after_hours_logins",
}

SIGNAL_DIRECTION = {
    "Declining Task Completion": "below",
    "Response Time Spike": "above",
    "Reduced Working Hours": "below",
    "Sustained Workload Elevation": "above",
}


def attribute(signals: list[Signal]) -> tuple[Attribution, ...]:
    """Ranked per-metric contributions, largest first.

    Shares sum to 1.0 when anything contributed, and the tuple is empty when
    nothing did -- an empty explanation is the correct output for "no risk was
    attributed", and is far better than a list of zeroes that reads like a
    finding.

    Ties break on metric name so the order is stable: a briefing that reshuffles
    its reasons between two identical runs is a briefing nobody can trust.
    """
    weighted = [(signal, signal_contribution(signal)) for signal in signals]
    total = sum(weight for _, weight in weighted)
    if total <= 0:
        return ()

    attributions = [
        Attribution(
            metric=SIGNAL_METRIC.get(signal.signal_name, signal.signal_name),
            contribution=weight / total,
            effect_size=weight,
            direction=SIGNAL_DIRECTION.get(signal.signal_name, ""),
            weeks=signal.weeks_detected,
        )
        for signal, weight in weighted
        if weight > 0
    ]

    return tuple(sorted(attributions, key=lambda a: (-a.contribution, a.metric)))


def leading_metric(attributions: tuple[Attribution, ...]) -> str | None:
    """The single largest contributor, or None when nothing contributed."""
    return attributions[0].metric if attributions else None
