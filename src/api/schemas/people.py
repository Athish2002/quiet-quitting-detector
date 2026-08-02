# src/api/schemas/people.py
# Response models for the routes that are about a person.
#
# See the package docstring in __init__.py for why these exist at all. The rule
# that shapes every model here: these fields are read back off disk, written by
# runs that may predate the current code and by providers that are not bound by
# it. A response model turns one unexpected value into a 500 for the whole
# request, so closed sets are COERCED rather than rejected -- a single bad
# memory file must not blank the cohort view.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BeforeValidator, ConfigDict, Field, field_validator

from src.api.schemas.base import ResponseModel
from src.domain.feedback import FeedbackVerdict
from src.domain.intervention import (
    InterventionAggregate,
    InterventionOutcome,
    InterventionType,
)
from src.domain.models import Attribution, Classification, Confidence
from src.evolution.registry import ModelVersion

#: Wrapped in list() because the type checker does not model StrEnum iteration
#: -- the same workaround as INTERVENTION_TYPE_VALUES in routers/evolution.py.
_CLASSIFICATION_BY_VALUE = {c.value.casefold(): c for c in list(Classification)}
_CONFIDENCE_BY_VALUE = {c.value.casefold(): c for c in list(Confidence)}


def _as_classification(value: object) -> object:
    """Map a stored classification onto the closed set.

    Every writer in this repository goes through `domain.risk.classify`, so this
    only bites on a record a provider wrote directly. That is a data-integrity
    problem, and the safe reading of an unrecognised state is not "Healthy" --
    it is "Watch", which prompts someone to look without asserting anything
    about the person.
    """
    if isinstance(value, Classification):
        return value
    if isinstance(value, str):
        return _CLASSIFICATION_BY_VALUE.get(
            value.strip().casefold(), Classification.WATCH
        )
    return Classification.WATCH


def _as_confidence(value: object) -> object:
    """An unrecognised confidence becomes absent, not a guess.

    Null renders as "not recorded" and suppresses nothing; inventing a level
    would either hide a caveat or add one that was never computed.
    """
    if value is None or isinstance(value, Confidence):
        return value
    if isinstance(value, str):
        return _CONFIDENCE_BY_VALUE.get(value.strip().casefold())
    return None


#: A classification as read back from storage.
StoredClassification = Annotated[Classification, BeforeValidator(_as_classification)]
#: A confidence level as read back from storage. None means none was recorded.
StoredConfidence = Annotated[Confidence | None, BeforeValidator(_as_confidence)]


class Signal(ResponseModel):
    """One detected behavioural pattern, in the shape it was stored in.

    Two shapes reach this model and both are real: `signal_name` from the trend
    detector, and `signal` from the orchestrator's MISSING_DATA_GAP marker.
    Neither is required, because a record written by an earlier run may carry
    only the other, and a 500 on the cohort view is a worse outcome than a field
    the UI has to fall back on.
    """

    model_config = ConfigDict(extra="allow")

    signal_name: str | None = None
    signal: str | None = None
    severity: str | None = None
    weeks_detected: list[int] = Field(default_factory=list)
    details: str | None = None

    @field_validator("weeks_detected", mode="before")
    @classmethod
    def _drop_junk_weeks(cls, value: object) -> object:
        """Keep the week numbers, discard anything else.

        The LLM enrichment path is allowed to rewrite this field, and it is not
        worth failing a response over: the week list is context for a manager,
        never an input to a calculation.
        """
        if isinstance(value, list):
            return [w for w in value if isinstance(w, int) and not isinstance(w, bool)]
        return []


class EmployeeWeek(ResponseModel):
    """One point on a person's own history line."""

    week: int
    score: int
    classification: StoredClassification


class EmployeeSummary(ResponseModel):
    """A person's latest evaluation, with their own history attached.

    `score_range` is deliberately not called a confidence interval, and it is
    absent rather than empty when there is none: an empty array is truthy in
    JavaScript, so the previous `[]` made the UI offer a range with no numbers
    in it.
    """

    name: str
    score: int
    classification: StoredClassification
    rationale: str = ""
    latest_week: int
    signals: list[Signal] = Field(default_factory=list)
    #: Null when no confidence was recorded, which the UI shows as such.
    confidence: StoredConfidence = None
    score_range: tuple[int, int] | None = None
    attributions: list[Attribution] = Field(default_factory=list)
    model_version: str | None = None
    #: True when this came from a degraded fallback tier rather than the scorer.
    degraded: bool = False
    history: list[EmployeeWeek] = Field(default_factory=list)

    @field_validator("score_range", mode="before")
    @classmethod
    def _absent_rather_than_empty(cls, value: object) -> object:
        return value or None


class BriefingView(ResponseModel):
    """A person's most recent manager briefing, or a note saying there is none."""

    found: bool
    briefing: str = ""
    #: The same markdown, under the name the console has always used for it.
    raw_card: str = ""


class RiskData(ResponseModel):
    """The scorer's own output for a hypothetical week, passed through.

    Permissive on purpose: this is whatever the active tier produced, and the
    what-if panel renders it rather than reasoning about it.
    """

    model_config = ConfigDict(extra="allow")

    score: int | None = None
    classification: str | None = None
    rationale: str | None = None
    confidence: str | None = None
    model_version: str | None = None
    provenance: str | None = None
    degraded: bool = False


class SimulationResult(ResponseModel):
    """A hypothetical employee-week, scored by the real agent chain."""

    success: bool
    employee_name: str
    signals: list[Signal] = Field(default_factory=list)
    risk_data: RiskData
    briefing: str = ""


class FeedbackAck(ResponseModel):
    status: Literal["recorded"] = "recorded"
    week: int
    verdict: FeedbackVerdict
    #: Which model made the call being judged. Calibration is per version.
    model_version: str = ""


class InterventionAck(ResponseModel):
    status: Literal["recorded"] = "recorded"
    week: int
    intervention: InterventionType


class InterventionTypes(ResponseModel):
    """A closed list. Free text here would record a private conversation."""

    types: list[InterventionType] = Field(default_factory=list)
    note: str = ""


class InterventionExample(InterventionOutcome):
    """One measured outcome, with the sentence a manager should read instead."""

    #: Extends the domain model rather than ResponseModel, so it opts into the
    #: same serialization-schema rule by hand. Pydantic merges this with the
    #: parent's config, which keeps the outcome frozen.
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    plain_english: str = ""


class InterventionOutcomes(ResponseModel):
    """Aggregated by TYPE of action, never by manager."""

    #: Permanently true, and a field rather than a comment so that no consumer
    #: can render these as causal.
    association_only: Literal[True] = True
    caveat: str = ""
    by_type: list[InterventionAggregate] = Field(default_factory=list)
    measured_outcomes: int = 0
    examples: list[InterventionExample] = Field(default_factory=list)


class ModelList(ResponseModel):
    active: str = ""
    versions: list[ModelVersion] = Field(default_factory=list)
