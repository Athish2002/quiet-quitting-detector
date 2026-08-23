# src/api/routers/evolution.py
# Feedback, interventions, calibration and the model registry.
#
# The Phase 3 and Phase 5 routes live here rather than in app.py, which is the
# pattern the rest of the routes follow as they are extracted. Handlers are thin:
# validate, call into `domain` or `evolution`, return. No business logic.

from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.api.schemas import (
    DriftView,
    FeedbackAck,
    InterventionAck,
    InterventionOutcomes,
    InterventionTypes,
    ModelList,
)
from src.app_utils.names import first_name_of
from src.domain.feedback import FeedbackReason, FeedbackRecord, FeedbackVerdict
from src.domain.intervention import (
    InterventionRecord,
    InterventionType,
    aggregate_by_type,
    describe_outcome,
    measure_outcome,
)
from src.domain.models import WeekMetrics
from src.domain.signals import METRIC_DIRECTION, build_personal_baselines
from src.domain.statistics import Direction
from src.evolution.calibration import CalibrationTracker
from src.evolution.feedback_store import FeedbackStore
from src.evolution.intervention_store import InterventionStore
from src.evolution.registry import ModelRegistry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["evolution"])

#: Materialised once: the type checker does not model StrEnum iteration.
INTERVENTION_TYPE_VALUES: list[str] = [t.value for t in list(InterventionType)]

MEMORY_DIR = os.path.join("data", "memory")
MIN_WEEK, MAX_WEEK = 1, 520


class FeedbackInput(BaseModel):
    """A manager's verdict on one briefing.

    No free-text field, by design. A notes box on a form about an employee is
    where health details and character judgements end up -- not through bad
    faith, but because a manager trying to be helpful writes them. CONTEXT.md
    rule 5 forbids that in agent memory, so the schema makes it impossible.
    """

    employee_name: str = Field(min_length=1, max_length=100)
    week: int = Field(ge=MIN_WEEK, le=MAX_WEEK)
    #: The enum rather than a pattern, so the closed set reaches the OpenAPI
    #: schema and the frontend's verdict buttons are checked against it.
    verdict: FeedbackVerdict
    #: Deliberately NOT the enum: an unrecognised reason degrades to
    #: `not_stated` below rather than rejecting a verdict a manager took the
    #: trouble to give.
    reason: str = "not_stated"


class InterventionInput(BaseModel):
    """What kind of action a manager took after a briefing.

    Also has no free-text field, and for a stronger reason: text here would be
    the contents of a private conversation between a manager and their report.
    See the feasibility note at the top of src/domain/intervention.py.
    """

    employee_name: str = Field(min_length=1, max_length=100)
    week: int = Field(ge=MIN_WEEK, le=MAX_WEEK)
    intervention: str


def _stored_evaluation(first_name: str, week: int) -> dict:
    path = os.path.join(MEMORY_DIR, f"{first_name}_week{week}.json")
    if not os.path.exists(path):
        raise HTTPException(
            status_code=404,
            detail="No evaluation on record for that person and week.",
        )
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        raise HTTPException(
            status_code=404, detail="That evaluation could not be read."
        ) from exc


@router.post(
    "/feedback",
    summary="Record a manager's verdict on a briefing",
    response_model=FeedbackAck,
)
def submit_feedback(payload: FeedbackInput) -> dict:
    """The ground-truth signal this system otherwise has no way to obtain."""
    first_name = first_name_of(payload.employee_name).lower()
    stored = _stored_evaluation(first_name, payload.week)

    try:
        reason = FeedbackReason(payload.reason)
    except ValueError:
        reason = FeedbackReason.NOT_STATED

    record = FeedbackStore().record(
        FeedbackRecord(
            subject_id=first_name,
            week=payload.week,
            predicted_score=int(stored.get("score", 1)),
            predicted_classification=str(stored.get("classification", "Healthy")),
            verdict=payload.verdict,
            reason=reason,
            model_version=str(stored.get("model_version", "unknown")),
        )
    )

    return {
        "status": "recorded",
        "week": record.week,
        "verdict": record.verdict.value,
        "model_version": record.model_version,
    }


INTERVENTION_ALIASES: dict[str, str] = {
    "workload_review": "workload_adjustment",
    "workload_adjustment": "workload_adjustment",
    "role_clarity_discussion": "role_or_goal_clarification",
    "role_clarity": "role_or_goal_clarification",
    "role_or_goal_clarification": "role_or_goal_clarification",
    "check_in": "check_in",
    "1_on_1": "check_in",
    "1-on-1": "check_in",
    "blocker_removed": "blocker_removed",
    "time_off_encouraged": "time_off_encouraged",
    "connected_to_support": "connected_to_support",
    "team_or_project_change": "team_or_project_change",
    "no_action_taken": "no_action_taken",
    "dismissed_no_action": "no_action_taken",
    "dismiss": "no_action_taken",
}


@router.post(
    "/interventions",
    summary="Record what kind of action a manager took",
    response_model=InterventionAck,
)
def submit_intervention(payload: InterventionInput) -> dict:
    first_name = first_name_of(payload.employee_name).lower()
    try:
        _stored_evaluation(first_name, payload.week)
    except HTTPException:
        logger.info(
            "Recording intervention for %s week %d without pre-existing disk memory snapshot.",
            first_name,
            payload.week,
        )

    raw_val = payload.intervention.strip().lower()
    canonical_val = INTERVENTION_ALIASES.get(raw_val, raw_val)

    try:
        kind = InterventionType(canonical_val)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                "Unknown intervention type. Allowed: "
                + ", ".join(sorted(INTERVENTION_TYPE_VALUES))
            ),
        ) from exc

    record = InterventionStore().record(
        InterventionRecord(subject_id=first_name, week=payload.week, intervention=kind)
    )
    return {
        "status": "recorded",
        "week": record.week,
        "intervention": record.intervention.value,
    }


@router.get(
    "/interventions/types",
    summary="The closed list of recordable action types",
    response_model=InterventionTypes,
)
def intervention_types() -> dict:
    return {
        "types": sorted(INTERVENTION_TYPE_VALUES),
        "note": (
            "A closed list on purpose. Free text here would record what was said "
            "in a private one-to-one."
        ),
    }


@router.get(
    "/interventions/outcomes",
    summary="What followed each kind of action (association, never causation)",
    response_model=InterventionOutcomes,
)
def intervention_outcomes() -> dict:
    """Aggregate outcomes by intervention TYPE.

    Never by manager. A per-manager effectiveness score would make this a
    performance tool for managers whose KPI is their reports' wellbeing metrics,
    which creates an immediate incentive to lean on whoever's numbers look bad.
    """
    store = InterventionStore()
    outcomes = []

    for record in store.all():
        timeline = _timeline_for(record.subject_id)
        if not timeline:
            continue
        baselines = build_personal_baselines(timeline)
        for metric, baseline in baselines.items():
            series = [
                (week.week, float(getattr(week, metric)))
                for week in timeline
                if getattr(week, metric, None) is not None
            ]
            outcome = measure_outcome(
                record,
                metric,
                baseline,
                series,
                concerning_below=METRIC_DIRECTION[metric] is Direction.BELOW,
            )
            if outcome is not None:
                outcomes.append(outcome)

    return {
        "association_only": True,
        "caveat": (
            "These are observational outcomes with no control group. People are "
            "flagged at their most extreme and tend to move back toward their own "
            "normal regardless of what anyone does, so the figures below report "
            "recovery BEYOND that expectation, not raw before/after change."
        ),
        # The response model serialises these; dumping them here first would
        # only be re-validated on the way out.
        "by_type": aggregate_by_type(outcomes),
        "measured_outcomes": len(outcomes),
        "examples": [
            {**o.model_dump(), "plain_english": describe_outcome(o)}
            for o in outcomes[:5]
        ],
    }


def _timeline_for(first_name: str) -> list[WeekMetrics]:
    """Rebuild one person's week timeline from stored evaluations."""
    weeks: list[WeekMetrics] = []
    if not os.path.isdir(MEMORY_DIR):
        return weeks

    for name in sorted(os.listdir(MEMORY_DIR)):
        if not name.startswith(f"{first_name}_week") or not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(MEMORY_DIR, name), encoding="utf-8") as fh:
                record = json.load(fh)
            metrics = record.get("metrics") or record.get("week_metrics")
            if metrics:
                weeks.append(WeekMetrics.model_validate(metrics))
        except Exception:
            logger.debug("Skipping unreadable memory file during timeline rebuild.")
    return sorted(weeks, key=lambda w: w.week)


@router.get("/calibration", summary="Is the system actually right?")
def get_calibration() -> DriftView:
    """Lifetime and recent calibration, reported separately.

    A tool that was accurate for six months and has been wrong for three weeks
    shows up as drift here rather than being averaged into a comfortable
    lifetime figure.

    Returns the tracker's own view rather than a dict rebuilt from it: the
    rebuild was one hand-copied field list away from disagreeing with the object
    it was copying.
    """
    active = ModelRegistry().active_version()
    return CalibrationTracker().drift(active_model_version=active)


@router.get(
    "/models",
    summary="Registered scoring models and which one is live",
    response_model=ModelList,
)
def list_models() -> dict:
    registry = ModelRegistry()
    return {
        "active": registry.active_version(),
        "versions": registry.versions(),
    }
