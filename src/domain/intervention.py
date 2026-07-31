# src/domain/intervention.py
# Did the manager's action help? -- measured honestly, or not at all.
#
# ---------------------------------------------------------------------------
# FEASIBILITY, stated up front because most of this request is not buildable
# ---------------------------------------------------------------------------
#
# The ask was: track manager action and impact, and determine whether a
# manager's advice or WORDS affected the employee. Three separable pieces, with
# three different answers.
#
# 1. "Did the manager act, and what kind of action?"            -- FEASIBLE.
#    A closed list of intervention types, recorded by the manager. Built here.
#
# 2. "Did the employee's own trajectory change afterwards?"     -- FEASIBLE,
#    with one large caveat that most implementations of this get wrong. See
#    REGRESSION TO THE MEAN below. Built here, with the correction.
#
# 3. "Did the manager's WORDS impact the employee?"             -- NOT BUILT,
#    and this file will not be extended to do it. Answering it requires
#    capturing what was said in a private 1-on-1. That is a recording of a
#    conversation between two people about one of them, which:
#      * violates CONTEXT.md rule 5 (behavioural signals only, never free text
#        about a person),
#      * is a categorical escalation from "we count tasks" to "we listen to
#        your meetings", and
#      * is the precise capability that makes people rightly afraid of software
#        like this. PRODUCTION_EVOLUTION_PROMPT.md 2 asks: "would I be
#        comfortable if this were run on me, and I read the audit log?" Nobody
#        is comfortable with a transcript of their manager's attempt to support
#        them being scored.
#    The nearest safe thing is what is built here: the manager states what KIND
#    of action they took, and the system reports what happened to that person's
#    own behavioural metrics afterwards. That answers the useful question --
#    which kinds of support tend to be followed by recovery -- without anybody
#    's words being recorded.
#
# ---------------------------------------------------------------------------
# REGRESSION TO THE MEAN -- why naive impact measurement is always wrong here
# ---------------------------------------------------------------------------
#
# This system flags people at their most extreme. That is its entire job. Now
# measure "did they improve after the manager spoke to them" and the answer
# comes back YES at a high rate -- for an intervention that did nothing at all,
# and even for one that actively hurt.
#
# The reason is arithmetic, not psychology. A person is flagged in the week
# their metrics sat furthest from their own normal. Next week's metrics are
# drawn from the same distribution and will, on average, sit closer to their
# normal, because extreme observations are extreme partly by chance. Improvement
# would appear if the manager had been on holiday.
#
# So a system that reported raw before/after change would tell every manager
# that their interventions work, would be believed, and would be wrong. It is
# worse than reporting nothing: it manufactures confidence in whatever the
# organisation happens to already do.
#
# What is computed instead is EXCESS recovery -- observed change minus the
# change expected from regression alone, using the person's own series to
# estimate how much of their week-to-week movement persists. Excess near zero
# means "this looks like what would have happened anyway". That is usually the
# honest answer and the system says it.
#
# ---------------------------------------------------------------------------
# WHAT THIS MODULE REFUSES TO COMPUTE
# ---------------------------------------------------------------------------
#
# Per-manager effectiveness. There is no function here that takes a manager and
# returns a score, and `test_intervention_module_exposes_no_manager_scoring`
# fails if one appears.
#
# The reason is the same one that governs src/domain/cohort.py. A per-manager
# effectiveness number turns this into a performance-management tool for
# managers, whose KPI is their reports' wellbeing metrics. The incentive that
# creates is immediate and obvious: a manager whose score depends on their
# reports' numbers recovering will lean on the people whose numbers look bad.
# The tool would then be causing the harm it was built to prevent, and it would
# be doing it through the person best placed to help.
#
# Aggregation is therefore by intervention TYPE only -- "workload adjustment is
# associated with recovery more often than a check-in alone" is a useful,
# publishable finding about practice. "Sam is a 62% manager" is not.

from __future__ import annotations

import statistics
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from src.domain.models import Confidence, MetricBaseline
from src.domain.statistics import effective_spread

#: Weeks of post-intervention data needed before an outcome is measurable.
#: Two, matching the confirmation floor: one week after a conversation is noise.
MIN_POST_WEEKS = 2

#: Outcomes of the same type needed before an aggregate is reported at all.
#: Below this the number would be a story about two people.
MIN_OUTCOMES_FOR_AGGREGATE = 5

#: Excess recovery below this (in spread units) is indistinguishable from
#: regression to the mean, and is reported as "no detectable effect" rather than
#: as a small positive.
NEGLIGIBLE_EXCESS = 0.25

#: Fallback persistence when a series is too short to estimate it. 0.5 is the
#: conservative middle: it attributes half of any observed recovery to
#: regression, so a real effect has to clear a meaningful bar.
DEFAULT_PERSISTENCE = 0.5


class InterventionType(StrEnum):
    """What the manager did. A closed list, for the same reason as
    `FeedbackReason`: a free-text box here would collect the contents of a
    private conversation."""

    CHECK_IN = "check_in"  # a supportive 1-on-1
    WORKLOAD_ADJUSTMENT = "workload_adjustment"
    ROLE_OR_GOAL_CLARIFICATION = "role_or_goal_clarification"
    BLOCKER_REMOVED = "blocker_removed"
    TIME_OFF_ENCOURAGED = "time_off_encouraged"
    CONNECTED_TO_SUPPORT = "connected_to_support"  # signposted, not diagnosed
    TEAM_OR_PROJECT_CHANGE = "team_or_project_change"
    NO_ACTION_TAKEN = "no_action_taken"


#: Recording that nothing was done is as valuable as recording that something
#: was. Without it the only comparison available is "acted vs no record", and
#: "no record" mixes together "did nothing" with "did something and forgot to
#: say so" -- which biases every aggregate upward.
CONTROL_TYPES = frozenset({InterventionType.NO_ACTION_TAKEN})


class InterventionRecord(BaseModel):
    """One manager action, logged against one flagged week.

    `subject_id` is the pseudonymous surrogate. There is no manager identifier
    and no free-text field, both by design.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    subject_id: str
    week: int = Field(ge=1)
    intervention: InterventionType
    recorded_at: str = ""


class InterventionOutcome(BaseModel):
    """What happened to one person's own metrics after one intervention.

    Every field is about that individual compared against their own history.
    Nothing here compares them to anybody else.
    """

    model_config = ConfigDict(frozen=True)

    subject_id: str
    week: int = Field(ge=1)
    intervention: InterventionType
    metric: str

    #: Movement toward the person's own normal, in spread units. Positive is
    #: recovery.
    observed_recovery: float
    #: How much of that was expected from regression to the mean alone.
    expected_from_regression: float
    #: The part not explained by regression. The only number worth reading.
    excess_recovery: float
    post_weeks: int = Field(ge=0)
    confidence: Confidence = Confidence.LOW

    #: Permanently True. This is an association between an action and a
    #: subsequent change, in observational data with no control group and no
    #: randomisation. It is not evidence that the action caused the change, and
    #: the field exists so no consumer can render this as though it were.
    association_only: bool = True

    @property
    def is_detectable(self) -> bool:
        """Whether anything survived the regression correction."""
        return abs(self.excess_recovery) >= NEGLIGIBLE_EXCESS

    @property
    def direction(self) -> str:
        if not self.is_detectable:
            return "no detectable change beyond what was expected anyway"
        return "improved" if self.excess_recovery > 0 else "declined further"


class InterventionAggregate(BaseModel):
    """What tends to follow one KIND of action, across many people."""

    model_config = ConfigDict(frozen=True)

    intervention: InterventionType
    sample_size: int = Field(ge=0)
    median_excess_recovery: float | None = None
    improved: int = Field(default=0, ge=0)
    declined: int = Field(default=0, ge=0)
    no_change: int = Field(default=0, ge=0)
    reportable: bool = False
    note: str = ""


def persistence(series: list[float]) -> float:
    """Lag-1 autocorrelation of a person's own series, clamped to [0, 1].

    This is what decides how much of an observed recovery is attributed to
    regression. A person whose weeks are strongly correlated (persistence near
    1) does not bounce back on their own, so a recovery is more likely to mean
    something. A person whose weeks are near-independent (near 0) bounces back
    constantly and a recovery means almost nothing.

    Returns DEFAULT_PERSISTENCE when the series is too short to estimate --
    conservative, because assuming low persistence would credit interventions
    for recoveries that were always going to happen.
    """
    if len(series) < 4:
        return DEFAULT_PERSISTENCE

    first, second = series[:-1], series[1:]
    try:
        mean_a = statistics.fmean(first)
        mean_b = statistics.fmean(second)
        covariance = sum(
            (a - mean_a) * (b - mean_b) for a, b in zip(first, second, strict=True)
        )
        spread_a = sum((a - mean_a) ** 2 for a in first) ** 0.5
        spread_b = sum((b - mean_b) ** 2 for b in second) ** 0.5
        if spread_a == 0 or spread_b == 0:
            return DEFAULT_PERSISTENCE
        return max(0.0, min(1.0, covariance / (spread_a * spread_b)))
    except (ValueError, ZeroDivisionError):  # pragma: no cover - guarded above
        return DEFAULT_PERSISTENCE


def expected_regression_recovery(
    flagged_value: float, baseline: MetricBaseline, series: list[float]
) -> float:
    """Recovery expected from regression to the mean alone, in spread units.

    A value sitting `d` away from the person's own centre is expected to sit
    `persistence * d` away next week purely because extremes are partly chance.
    The difference is recovery that requires no explanation.
    """
    spread = effective_spread(baseline)
    deviation = (flagged_value - baseline.centre) / spread
    return abs(deviation) * (1.0 - persistence(series))


def measure_outcome(
    record: InterventionRecord,
    metric: str,
    baseline: MetricBaseline,
    series: list[tuple[int, float]],
    *,
    concerning_below: bool = True,
) -> InterventionOutcome | None:
    """Measure what followed one intervention for one metric.

    `series` is the person's own (week, value) history, chronological. Returns
    None when there is not enough post-intervention data to say anything, which
    is the correct and common answer -- an intervention two weeks ago has not
    had time to be measurable.
    """
    ordered = sorted(series, key=lambda item: item[0])
    values = [value for _, value in ordered]

    flagged = next((v for w, v in ordered if w == record.week), None)
    after = [v for w, v in ordered if w > record.week]

    if flagged is None or len(after) < MIN_POST_WEEKS:
        return None

    spread = effective_spread(baseline)

    def recovery(value: float) -> float:
        """Movement in the non-concerning direction, positive for recovery.

        Directional, not absolute. An earlier version compared |deviation|
        before and after, which scored someone who recovered PAST their own
        normal as barely recovering at all -- the person most clearly helped
        looked like the person least helped.

        Deliberately not capped at "returned to normal". Overshooting into the
        opposite problem is a real thing (hours climbing into overwork), but it
        is a separate signal with its own detector, and suppressing it here
        would only hide it.
        """
        before = (flagged - baseline.centre) / spread
        now = (value - baseline.centre) / spread
        return (now - before) if concerning_below else (before - now)

    # Median of the post window rather than the next single week: one good week
    # after a conversation is exactly the noise this whole module exists to
    # avoid mistaking for an effect.
    observed = statistics.median([recovery(v) for v in after])
    expected = expected_regression_recovery(flagged, baseline, values)

    return InterventionOutcome(
        subject_id=record.subject_id,
        week=record.week,
        intervention=record.intervention,
        metric=metric,
        observed_recovery=observed,
        expected_from_regression=expected,
        excess_recovery=observed - expected,
        post_weeks=len(after),
        confidence=_outcome_confidence(len(after), len(values)),
    )


def _outcome_confidence(post_weeks: int, total_weeks: int) -> Confidence:
    """Deliberately pessimistic: this is observational data about one person."""
    if post_weeks < MIN_POST_WEEKS or total_weeks < 6:
        return Confidence.LOW
    if post_weeks >= 4 and total_weeks >= 10:
        return Confidence.MODERATE
    return Confidence.LOW


def aggregate_by_type(
    outcomes: list[InterventionOutcome],
) -> list[InterventionAggregate]:
    """What tends to follow each KIND of action.

    By type, never by manager -- see the module note. Types with too few
    outcomes are returned with `reportable=False` and no numbers, rather than
    omitted: knowing that a practice has not been evaluated is itself useful,
    and silently dropping it would let a reader assume it had been.
    """
    grouped: dict[InterventionType, list[InterventionOutcome]] = {}
    for outcome in outcomes:
        grouped.setdefault(outcome.intervention, []).append(outcome)

    aggregates: list[InterventionAggregate] = []
    for intervention, group in grouped.items():
        if len(group) < MIN_OUTCOMES_FOR_AGGREGATE:
            aggregates.append(
                InterventionAggregate(
                    intervention=intervention,
                    sample_size=len(group),
                    reportable=False,
                    note=(
                        f"Only {len(group)} measured outcome(s). Too few to say "
                        "anything about this practice."
                    ),
                )
            )
            continue

        improved = sum(1 for o in group if o.is_detectable and o.excess_recovery > 0)
        declined = sum(1 for o in group if o.is_detectable and o.excess_recovery < 0)

        aggregates.append(
            InterventionAggregate(
                intervention=intervention,
                sample_size=len(group),
                median_excess_recovery=statistics.median(
                    [o.excess_recovery for o in group]
                ),
                improved=improved,
                declined=declined,
                no_change=len(group) - improved - declined,
                reportable=True,
                note=(
                    "Association only. These are observational outcomes with no "
                    "control group; they describe what tended to follow this "
                    "kind of action, not what it caused."
                ),
            )
        )

    return sorted(aggregates, key=lambda a: a.intervention.value)


def describe_outcome(outcome: InterventionOutcome) -> str:
    """A sentence a manager can read without being misled.

    Leads with the caveat rather than burying it. The number is meaningless
    without "beyond what was expected anyway", and a reader who takes only the
    first clause should still take away something true.
    """
    if not outcome.is_detectable:
        return (
            "No change beyond what would have been expected anyway. Most weeks "
            "after a flag look like this, because people flagged at their worst "
            "tend to move back toward their own normal regardless."
        )

    direction = "better" if outcome.excess_recovery > 0 else "worse"
    return (
        f"Moved {direction} by {abs(outcome.excess_recovery):.1f} beyond the "
        "recovery expected from normal week-to-week variation. This is an "
        "association in observational data, not evidence that the action caused "
        "it."
    )
