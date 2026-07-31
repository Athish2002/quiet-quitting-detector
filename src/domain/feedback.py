# src/domain/feedback.py
# Manager feedback and calibration (PRODUCTION_EVOLUTION_PROMPT.md 6.2).
#
# "Managers can mark a briefing accurate / not accurate / harmful, with optional
#  structured reason. Store it. This is the ground-truth signal the system
#  currently lacks entirely."
#
# That last clause is the important one. Until now this system has produced
# thousands of judgements about people and never once found out whether any of
# them were right. It could have been wrong about everybody, in the same
# direction, for a year, and nothing in the codebase would have noticed. Every
# other part of 6.2 -- retraining, promotion gates, calibration -- is downstream
# of having this signal at all.
#
# The HARMFUL verdict is not a third severity of "wrong". A briefing can be
# perfectly accurate and still have damaged someone: correct about a decline,
# and it turned out the person was caring for a dying parent. Accuracy and harm
# are independent axes, and collapsing them into one scale would mean the
# system's own metrics could improve while the harm it caused went up.
#
# Everything here is pure. The store lives in src/evolution/.

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class FeedbackVerdict(StrEnum):
    ACCURATE = "accurate"
    NOT_ACCURATE = "not_accurate"
    HARMFUL = "harmful"


class FeedbackReason(StrEnum):
    """Structured reasons. A closed list, deliberately.

    Free text would collect exactly what CONTEXT.md rule 5 forbids from agent
    memory -- health details, opinions about character, "she's been difficult
    since the reorg". A closed list cannot hold any of that, and it is also the
    only form the calibration maths can actually aggregate.
    """

    KNOWN_LEAVE = "known_leave"  # approved holiday, sabbatical, parental leave
    KNOWN_SCHEDULE_CHANGE = "known_schedule_change"  # agreed part-time, compressed week
    ROLE_CHANGE = "role_change"  # different work, so different metrics
    TEAM_EVENT = "team_event"  # outage, reorg, offsite -- affected everyone
    DATA_PROBLEM = "data_problem"  # the numbers themselves were wrong
    TOO_LATE = "too_late"  # real, but the manager already knew
    TOO_SENSITIVE = "too_sensitive"  # should not have been surfaced at all
    NOT_STATED = "not_stated"


#: Reasons that indicate the SYSTEM was at fault rather than the world being
#: complicated. Used to separate "we got it wrong" from "we were right and it
#: didn't help", which need completely different fixes.
SYSTEM_FAULT_REASONS = frozenset(
    {
        FeedbackReason.KNOWN_LEAVE,
        FeedbackReason.KNOWN_SCHEDULE_CHANGE,
        FeedbackReason.ROLE_CHANGE,
        FeedbackReason.TEAM_EVENT,
        FeedbackReason.DATA_PROBLEM,
    }
)


class FeedbackRecord(BaseModel):
    """One manager's verdict on one briefing.

    `subject_id` is the pseudonymous surrogate, never a name (CONTEXT.md rule 1).
    There is no free-text field, by design -- see FeedbackReason.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    subject_id: str
    week: int = Field(ge=1)
    predicted_score: int = Field(ge=1, le=10)
    predicted_classification: str
    verdict: FeedbackVerdict
    reason: FeedbackReason = FeedbackReason.NOT_STATED
    #: Which scoring model produced the prediction being judged. Without this a
    #: calibration figure cannot be attributed to a version, and a regression
    #: cannot be traced to the change that caused it.
    model_version: str = "unknown"
    recorded_at: str = ""

    @property
    def was_elevated(self) -> bool:
        return self.predicted_classification.strip().casefold() != "healthy"

    @property
    def blames_the_system(self) -> bool:
        return (
            self.verdict is not FeedbackVerdict.ACCURATE
            and self.reason in SYSTEM_FAULT_REASONS
        )


class CalibrationReport(BaseModel):
    """Whether the system's confident calls correspond to reality.

    "A system that quietly becomes miscalibrated is worse than no system" (6.2).
    Worse, specifically, because people act on it: an uncalibrated tool that
    nobody trusts gets ignored, while an uncalibrated tool that everybody trusts
    changes how managers treat their reports.
    """

    model_config = ConfigDict(frozen=True)

    total: int = Field(default=0, ge=0)
    accurate: int = Field(default=0, ge=0)
    not_accurate: int = Field(default=0, ge=0)
    harmful: int = Field(default=0, ge=0)

    #: Of the briefings the system raised as elevated, the share managers
    #: confirmed. This is precision on the only calls that carry consequences --
    #: nobody is harmed by an unnoticed "Healthy".
    elevated_precision: float | None = None
    #: Share of ALL feedback marked harmful. Tracked separately and never netted
    #: off against accuracy.
    harm_rate: float = 0.0
    #: Share of the wrong calls the system itself caused, as opposed to the
    #: world being more complicated than the data.
    system_fault_rate: float | None = None

    @property
    def is_actionable(self) -> bool:
        """Whether there is enough feedback for the numbers to mean anything."""
        return self.total >= MIN_FEEDBACK_FOR_CALIBRATION


#: Below this, calibration figures are noise and must not be shown as a
#: percentage next to a trend line. Three managers disagreeing is a conversation,
#: not a 33% accuracy rate.
MIN_FEEDBACK_FOR_CALIBRATION = 10

#: Precision below this on elevated calls means the tool is crying wolf. Wired
#: into the promotion gate in src/evolution/registry.py.
MIN_ACCEPTABLE_PRECISION = 0.60

#: Any harm rate above this is a stop-and-review threshold. Set low on purpose:
#: one briefing in twenty causing harm is not an acceptable operating point for
#: a system pointed at people who did not ask to be measured.
MAX_ACCEPTABLE_HARM_RATE = 0.05


def compute_calibration(records: list[FeedbackRecord]) -> CalibrationReport:
    """Aggregate manager verdicts into a calibration picture.

    Deliberately does not produce a single "accuracy" number. A tool that is 90%
    accurate and harmful 10% of the time is not a good tool, and one figure
    would let the second fact hide behind the first.
    """
    if not records:
        return CalibrationReport()

    total = len(records)
    accurate = sum(1 for r in records if r.verdict is FeedbackVerdict.ACCURATE)
    not_accurate = sum(1 for r in records if r.verdict is FeedbackVerdict.NOT_ACCURATE)
    harmful = sum(1 for r in records if r.verdict is FeedbackVerdict.HARMFUL)

    elevated = [r for r in records if r.was_elevated]
    elevated_precision = (
        sum(1 for r in elevated if r.verdict is FeedbackVerdict.ACCURATE)
        / len(elevated)
        if elevated
        else None
    )

    wrong = [r for r in records if r.verdict is not FeedbackVerdict.ACCURATE]
    system_fault_rate = (
        sum(1 for r in wrong if r.blames_the_system) / len(wrong) if wrong else None
    )

    return CalibrationReport(
        total=total,
        accurate=accurate,
        not_accurate=not_accurate,
        harmful=harmful,
        elevated_precision=elevated_precision,
        harm_rate=harmful / total,
        system_fault_rate=system_fault_rate,
    )


def is_regression(candidate: CalibrationReport, incumbent: CalibrationReport) -> bool:
    """Whether a candidate model is worse than the one already in production.

    Asymmetric on purpose. Precision must *hold or improve* to promote, but ANY
    increase in harm blocks promotion regardless of how much precision improved.
    A model that finds more true positives by writing briefings that hurt people
    more often has not got better at this job.
    """
    if candidate.harm_rate > incumbent.harm_rate:
        return True
    if candidate.elevated_precision is None or incumbent.elevated_precision is None:
        return False
    return candidate.elevated_precision < incumbent.elevated_precision


def needs_review(report: CalibrationReport) -> bool:
    """Whether the running system has drifted far enough to stop and look."""
    if not report.is_actionable:
        return False
    if report.harm_rate > MAX_ACCEPTABLE_HARM_RATE:
        return True
    return (
        report.elevated_precision is not None
        and report.elevated_precision < MIN_ACCEPTABLE_PRECISION
    )
