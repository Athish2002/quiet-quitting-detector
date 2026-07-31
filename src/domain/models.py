# src/domain/models.py
# Typed boundary objects. Pydantic v2, no I/O.
#
# The pipeline previously passed raw `dict` between every layer, so a typo in a
# key was a silent None rather than an error, and nothing documented which keys
# a "week" was supposed to have. These models are the contract.
#
# Every metric is Optional by design: missing data is a gap, never a zero
# (CONTEXT.md rule 3). Defaulting an absent task count to 0 fabricates the exact
# signal this system exists to detect.

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Classification(StrEnum):
    HEALTHY = "Healthy"
    WATCH = "Watch"
    AT_RISK = "At Risk"
    SILENT_EXIT = "Silent Exit"


#: Classifications that count as "elevated" for recurrence purposes.
ELEVATED = frozenset(
    {Classification.WATCH, Classification.AT_RISK, Classification.SILENT_EXIT}
)


class WeekMetrics(BaseModel):
    """One employee-week. Only allowlisted, non-prohibited fields appear here.

    `sick_days`, `task_accuracy` and `sentiment` are deliberately absent -- they
    are prohibited by config/data_allowlist.json (health data, performance
    metric, emotion inference). Their absence from this model is a structural
    guarantee that no domain calculation can consume them.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    week: int = Field(ge=1)
    completed_tasks: int | None = Field(default=None, ge=0)
    response_time: float | None = Field(default=None, ge=0)
    after_hours_logins: int | None = Field(default=None, ge=0)
    weekly_hours: float | None = Field(default=None, ge=0)
    data_missing: bool = False

    @property
    def is_usable(self) -> bool:
        return not self.data_missing and any(
            v is not None
            for v in (
                self.completed_tasks,
                self.response_time,
                self.after_hours_logins,
                self.weekly_hours,
            )
        )


class Baseline(BaseModel):
    """The reference a person is compared against -- always their OWN history.

    Never a cohort or team average. Comparing people to each other is what makes
    a tool like this unfair: a parent on a school schedule, an engineer in
    another timezone, and someone in deep focus all look "disengaged" against a
    team mean and none of them are.
    """

    model_config = ConfigDict(frozen=True)

    completed_tasks: int | None = None
    response_time: float | None = None
    after_hours_logins: int | None = None
    weekly_hours: float | None = None

    @classmethod
    def from_week(cls, week: WeekMetrics) -> Baseline:
        return cls(
            completed_tasks=week.completed_tasks,
            response_time=week.response_time,
            after_hours_logins=week.after_hours_logins,
            weekly_hours=week.weekly_hours,
        )


class Signal(BaseModel):
    """A behavioural pattern confirmed over 2+ consecutive weeks."""

    model_config = ConfigDict(frozen=True)

    signal_name: str
    weeks_detected: tuple[int, ...] = ()
    severity: Severity = Severity.MEDIUM
    #: Wellbeing signals may prompt a check-in but must never raise risk.
    wellbeing_only: bool = False
    #: Supportive prose added by an enricher. Never used in any calculation --
    #: scoring must not depend on what a language model happened to write.
    details: str = ""


class HistoryRecord(BaseModel):
    """A prior week's stored evaluation, as read back from memory."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    score: int = Field(ge=1, le=10)
    classification: str
    healthy_streak: int = Field(default=0, ge=0)

    @property
    def is_elevated(self) -> bool:
        return self.classification.strip().casefold() in {
            c.value.casefold() for c in ELEVATED
        }

    @property
    def is_healthy(self) -> bool:
        return self.classification.strip().casefold() == "healthy"


class Confidence(StrEnum):
    """How much weight the evidence can actually carry.

    This is not decoration. A manager shown "6/10, At Risk" acts on it; a manager
    shown "6/10, but we have two weeks of patchy data" asks a question instead.
    The second conversation is the one this system exists to cause.
    """

    NONE = "none"  # nothing usable -- do not present a number at all
    LOW = "low"  # too few observations, or too much missing data
    MODERATE = "moderate"
    HIGH = "high"


class MetricBaseline(BaseModel):
    """One metric's normal range for one person, as a distribution.

    `centre` is the median and `spread` the median absolute deviation, both over
    that person's own history and nobody else's.
    """

    model_config = ConfigDict(frozen=True)

    centre: float
    spread: float = Field(ge=0)
    observations: int = Field(ge=0)
    #: False when there were too few weeks for the distribution to mean much.
    #: The baseline is still returned -- the caller must lower confidence rather
    #: than pretend the question is unanswerable.
    is_distributional: bool = False


class Deviation(BaseModel):
    """One metric's departure from one person's own normal, in one week."""

    model_config = ConfigDict(frozen=True)

    metric: str
    week: int = Field(ge=1)
    observed: float
    baseline_centre: float
    #: Magnitude in units of the person's own variability, never negative.
    effect_size: float = Field(ge=0)
    #: The same departure as a plain proportion, for prose a manager can picture.
    relative_change: float
    significant: bool = False


class Attribution(BaseModel):
    """How much one metric contributed to the score, and which way.

    Required by 6.1's counterfactual layer: a briefing has to be able to say WHY,
    and a wrong call has to be debuggable. A score with no attribution is an
    accusation with no evidence attached.
    """

    model_config = ConfigDict(frozen=True)

    metric: str
    #: Share of the total risk contribution, 0-1. Shares sum to 1 when any
    #: contribution exists.
    contribution: float = Field(ge=0, le=1)
    effect_size: float = Field(ge=0)
    direction: str = ""
    weeks: tuple[int, ...] = ()


class RiskAssessment(BaseModel):
    """The outcome of scoring one week."""

    model_config = ConfigDict(frozen=True)

    score: int = Field(ge=1, le=10)
    classification: str
    rationale: str = ""
    healthy_streak: int = Field(default=0, ge=0)
    recurrence_applied: bool = False
    #: True when the evidence is too thin to be confident -- consumers must
    #: soften the briefing rather than present a number built on almost nothing.
    insufficient_data: bool = False

    confidence: Confidence = Confidence.MODERATE
    #: Heuristic plausible range for the score, NOT a frequentist confidence
    #: interval -- it is derived from how much evidence there is, not from a
    #: sampling distribution. Named and documented this way on purpose: calling
    #: a rule-of-thumb band a "95% CI" would be the exact kind of borrowed
    #: authority this system must not trade on. See docs/LIMITATIONS.md.
    score_range: tuple[int, int] | None = None
    #: Ranked per-metric contributions, largest first.
    attributions: tuple[Attribution, ...] = ()
