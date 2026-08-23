# src/api/routers/simulator.py
# The what-if evaluator and synthetic-data generator.
from __future__ import annotations

import csv
import glob
import json
import logging
import os
import random

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.api.paths import MEMORY_DIR, SIMULATOR_MEMORY_DIR, WEEKLY_DIR, ensure
from src.api.schemas import MockDataResult, SimulationResult
from src.app_utils.audit_log import log_event
from src.app_utils.names import first_name_of
from src.data_layer.ingestion import CANONICAL_HEADER, MAX_WEEK, MIN_WEEK

logger = logging.getLogger(__name__)
router = APIRouter(tags=["simulator"])

ARCHETYPES = ("Silent Exit", "At Risk", "Watch", "Healthy")
DEMO_EMPLOYEES = ("Arjun", "Priya", "Karthik", "Divya", "Ravi", "Meena")


class CustomEvaluatorInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    week_number: int = Field(ge=MIN_WEEK, le=MAX_WEEK)
    tasks_completed: int = Field(ge=0, le=1000)
    avg_response_time: float = Field(ge=0, le=1000)
    after_hours_logins: int = Field(ge=0, le=100)
    previous_classification: str = Field(default="Healthy", max_length=50)
    consecutive_weeks_elevated: int = Field(default=0, ge=0, le=1000)
    weekly_hours: int = Field(default=40, ge=0, le=168)


@router.post(
    "/score/custom",
    summary="Evaluate one hypothetical employee-week",
    response_model=SimulationResult,
)
def score_custom_employee(data: CustomEvaluatorInput) -> dict:
    from src.manager_briefing_agent import generate_briefing
    from src.risk_scorer_agent import score_risk
    from src.trend_detector_agent import detect_trends

    name = first_name_of(data.name.strip()).capitalize()
    name_lower = name.lower()

    ensure(SIMULATOR_MEMORY_DIR)
    for stale in glob.glob(
        os.path.join(SIMULATOR_MEMORY_DIR, f"{name_lower}_week*.json")
    ):
        os.remove(stale)

    if data.previous_classification != "Healthy":
        _write_mock_history(
            name_lower,
            data.week_number,
            data.previous_classification,
            max(1, data.consecutive_weeks_elevated),
        )

    baseline = {
        "week": 1,
        "completed_tasks": 25,
        "response_time": 2.0,
        "after_hours_logins": 0,
        "weekly_hours": 40,
    }

    target_week = max(2, data.week_number)
    elevated_count = max(1, data.consecutive_weeks_elevated) if data.previous_classification != "Healthy" else 1

    history = [baseline]
    for w in range(2, target_week):
        if w >= target_week - elevated_count:
            history.append({
                "week": w,
                "completed_tasks": data.tasks_completed,
                "response_time": data.avg_response_time,
                "after_hours_logins": data.after_hours_logins,
                "weekly_hours": data.weekly_hours,
            })
        else:
            history.append({"week": w, "completed_tasks": 25, "response_time": 2.0, "after_hours_logins": 0, "weekly_hours": 40})

    history.append({
        "week": target_week,
        "completed_tasks": data.tasks_completed,
        "response_time": data.avg_response_time,
        "after_hours_logins": data.after_hours_logins,
        "weekly_hours": data.weekly_hours,
    })

    current_week_metrics = {
        "completed_tasks": data.tasks_completed,
        "response_time": data.avg_response_time,
        "after_hours_logins": data.after_hours_logins,
        "weekly_hours": data.weekly_hours,
    }

    try:
        signals = detect_trends(
            name,
            history,
        )
        risk_data = score_risk(
            name,
            signals,
            target_week,
            memory_dir=SIMULATOR_MEMORY_DIR,
        )
        briefing = generate_briefing(
            name, signals, risk_data, memory_dir=SIMULATOR_MEMORY_DIR
        )
    except Exception as exc:
        logger.exception("Simulator evaluation error: %s", exc)
        raise HTTPException(
            status_code=500, detail="The evaluation could not be completed."
        ) from exc

    return {
        "success": True,
        "employee_name": name,
        "signals": signals,
        "risk_data": risk_data,
        "briefing": briefing or "No briefing required (Healthy status).",
    }


_MOCK_SCORES = {"At Risk": 6, "Silent Exit": 8}


def _write_mock_history(
    name_lower: str, week_number: int, classification: str, weeks: int
) -> None:
    for offset in range(weeks):
        previous_week = week_number - 1 - offset
        if previous_week <= 0:
            continue
        record = {
            "score": _MOCK_SCORES.get(classification, 4),
            "classification": classification,
            "rationale": "Mocked historical classification.",
            "healthy_streak": 0,
        }
        path = os.path.join(
            SIMULATOR_MEMORY_DIR, f"{name_lower}_week{previous_week}.json"
        )
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2)


def _assign_archetype(rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.15:
        return "Silent Exit"
    if roll < 0.30:
        return "At Risk"
    if roll < 0.45:
        return "Watch"
    return "Healthy"


def _week_metrics(
    archetype: str, week: int, rng: random.Random
) -> tuple[int, float, int, int]:
    if archetype == "Silent Exit":
        return (
            max(1, 10 - int(week * 2.5) + rng.randint(-1, 1)),
            round(max(0.5, 0.4 + week * 1.2 + rng.uniform(-0.4, 0.6)), 2),
            rng.randint(1, max(1, week)),
            max(35, 45 - (week * 2) + rng.randint(-2, 2)),
        )
    if archetype == "At Risk":
        return (
            max(2, 10 - int(week * 1.5) + rng.randint(-2, 1)),
            round(max(0.4, 0.5 + week * 0.6 + rng.uniform(-0.2, 0.4)), 2),
            rng.randint(0, max(1, week - 1)),
            int(max(38, 48 - (week * 1.5) + rng.randint(-3, 3))),
        )
    if archetype == "Watch":
        if week == 3:
            return (rng.randint(4, 6), round(rng.uniform(1.5, 2.5), 2), rng.randint(1, 2), rng.randint(50, 60))
        if week == 4:
            return (rng.randint(8, 10), round(rng.uniform(0.5, 1.2), 2), 0, rng.randint(40, 42))
        return (max(5, 10 - week + rng.randint(-1, 0)), round(0.5 + week * 0.3 + rng.uniform(-0.1, 0.2), 2), 0, rng.randint(42, 48))
    return (rng.randint(8, 11), round(max(0.2, 0.4 + rng.uniform(-0.15, 0.2)), 2), rng.choice([0, 0, 1]), rng.randint(38, 42))


_BASE_SCORES = {
    "Silent Exit": {1: 3, 2: 6, 3: 8},
    "At Risk": {1: 2, 2: 4, 3: 6},
    "Watch": {1: 2, 2: 3, 3: 4},
}


def _mock_signals(tasks: int, response: float, after_hours: int, week: int) -> list[dict]:
    signals = []
    if tasks < 7:
        signals.append({"signal_name": "Declining Task Completion", "weeks_detected": [week], "severity": "medium" if tasks >= 4 else "high"})
    if response > 1.5:
        signals.append({"signal_name": "Response Time Spike", "weeks_detected": [week], "severity": "high" if response > 2.2 else "medium"})
    if after_hours > 2:
        signals.append({"signal_name": "Sustained Workload Elevation", "weeks_detected": [week], "severity": "medium"})
    return signals


def _classify_mock(score: int, tasks: int, response: float, hours: int) -> tuple[str, str]:
    if score <= 2:
        return "Healthy", f"Operational baseline assessment. Stable task volume ({tasks}) and standard latency."
    if score <= 4:
        return "Watch", f"Early indicator check. Elevated response time ({response}h) against personal baseline."
    if score <= 7:
        return "At Risk", f"Disengagement warning. Persistent declines in tasks and low hours ({hours}h)."
    return "Silent Exit", "Severe disengagement flags. Consecutive drop in output and communication latency spikes."


DEFAULT_SEED = 20260801


class MockDataInput(BaseModel):
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)


@router.post(
    "/mock-data",
    summary="Regenerate the synthetic demo cohort",
    response_model=MockDataResult,
)
def generate_mock_data(data: MockDataInput | None = None) -> dict:
    seed = data.seed if data and data.seed is not None else DEFAULT_SEED
    rng = random.Random(seed)

    try:
        ensure(WEEKLY_DIR, MEMORY_DIR)
        for stale in glob.glob(os.path.join(WEEKLY_DIR, "*.csv")):
            os.remove(stale)
        for stale in glob.glob(os.path.join(MEMORY_DIR, "*.json")):
            os.remove(stale)

        profiles = {name: _assign_archetype(rng) for name in DEMO_EMPLOYEES}

        # Generate 52 weeks (4 Quarters of 13 weeks each)
        for week in range(1, 53):
            _write_week(week, profiles, rng)

        log_event("mock_data", "main", "Generated 52-week multi-quarter demo cohort.")
        return {
            "success": True,
            "message": f"Generated 52-week multi-quarter demo cohort from seed {seed}.",
            "seed": seed,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail="Failed to generate mock data."
        ) from exc


def _write_week(week: int, profiles: dict[str, str], rng: random.Random) -> None:
    path = os.path.join(WEEKLY_DIR, f"week{week}.csv")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(CANONICAL_HEADER)

        for employee, archetype in profiles.items():
            tasks, response, after_hours, hours = _week_metrics(archetype, week, rng)
            writer.writerow([employee, int(tasks), response, after_hours, int(hours)])

            base = _BASE_SCORES.get(archetype, {}).get(min(week, 3), 1)
            score = max(1, min(10, base + rng.randint(-1, 1)))
            classification, rationale = _classify_mock(score, tasks, response, hours)
            
            task_delta = min(1.0, max(0.05, round((25 - tasks) / 25.0, 2))) if tasks < 20 else 0.05
            resp_delta = min(1.0, max(0.05, round((response - 1.5) / 10.0, 2))) if response > 1.5 else 0.05
            hours_delta = min(1.0, max(0.05, round(abs(hours - 40) / 40.0, 2)))
            after_delta = min(1.0, max(0.05, round(after_hours / 20.0, 2))) if after_hours > 0 else 0.0

            attributions = [
                {"metric": "tasks", "contribution": task_delta, "effect_size": task_delta if tasks < 20 else -0.05, "direction": "below" if tasks < 20 else "normal"},
                {"metric": "response_time", "contribution": resp_delta, "effect_size": resp_delta if response > 1.5 else 0.05, "direction": "above" if response > 1.5 else "normal"},
                {"metric": "weekly_hours", "contribution": hours_delta, "effect_size": hours_delta if hours < 38 else 0.05, "direction": "below" if hours < 38 else ("above" if hours > 44 else "normal")},
                {"metric": "after_hours_logins", "contribution": after_delta, "effect_size": after_delta if after_hours > 2 else 0.05, "direction": "above" if after_hours > 2 else "normal"},
            ]

            record = {
                "score": score,
                "classification": classification,
                "rationale": rationale,
                "confidence": "high" if week >= 4 else "moderate",
                "healthy_streak": week if score <= 2 else 0,
                "signals": _mock_signals(tasks, response, after_hours, week),
                "attributions": attributions,
                "model_version": "gemini-2.5-flash",
                "degraded": False,
            }
            memory_path = os.path.join(MEMORY_DIR, f"{employee.lower()}_week{week}.json")
            with open(memory_path, "w", encoding="utf-8") as mf:
                json.dump(record, mf, indent=2)
