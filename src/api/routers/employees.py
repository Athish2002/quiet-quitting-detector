# src/api/routers/employees.py
# Reading back what the pipeline concluded about people.
#
# The main-cohort and realtime handlers were two near-identical 60-line copies
# in app.py. They are one function here parameterised by directory: a second
# copy is a second place for the "latest week wins" rule, the default score, and
# the history shape to drift -- and a divergence between them would mean the two
# tabs of the same dashboard disagreeing about the same person.

from __future__ import annotations

import glob
import json
import logging
import os

from fastapi import APIRouter, HTTPException

from src.api.paths import MEMORY_DIR, REALTIME_MEMORY_DIR, memory_dir_for

logger = logging.getLogger(__name__)

router = APIRouter(tags=["employees"])


def _load_weeks(memory_dir: str) -> dict[str, dict[int, dict]]:
    """Every stored evaluation, grouped by display name then week."""
    records: dict[str, dict[int, dict]] = {}
    if not os.path.exists(memory_dir):
        return records

    for path in glob.glob(os.path.join(memory_dir, "*.json")):
        parts = os.path.basename(path).replace(".json", "").split("_week")
        if len(parts) != 2:
            continue
        try:
            week = int(parts[1])
        except ValueError:
            continue

        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            # One corrupt file must not blank the whole cohort view.
            logger.debug("Skipping unreadable memory file.", exc_info=True)
            continue

        records.setdefault(parts[0].capitalize(), {})[week] = data

    return records


def _summarise(memory_dir: str) -> list[dict]:
    """Latest classification per person, plus their own week-by-week history."""
    summary = []
    for name, weeks in _load_weeks(memory_dir).items():
        if not weeks:
            continue
        latest = weeks[max(weeks)]
        summary.append(
            {
                "name": name,
                "score": latest.get("score", 1),
                "classification": latest.get("classification", "Healthy"),
                "rationale": latest.get("rationale", ""),
                "latest_week": max(weeks),
                "signals": latest.get("signals", []),
                # Phase 2/3 fields travel with the score so a consumer cannot
                # render the number without its caveat.
                "confidence": latest.get("confidence"),
                "score_range": latest.get("score_range"),
                "attributions": latest.get("attributions", []),
                "model_version": latest.get("model_version"),
                "degraded": latest.get("degraded", False),
                "history": [
                    {
                        "week": week,
                        "score": weeks[week].get("score", 1),
                        "classification": weeks[week].get("classification", "Healthy"),
                    }
                    for week in sorted(weeks)
                ],
            }
        )

    summary.sort(key=lambda entry: entry["name"])
    return summary


@router.get("/employees", summary="Latest status for the main cohort")
def get_employees_status() -> list[dict]:
    return _summarise(MEMORY_DIR)


@router.get("/employees/realtime", summary="Latest status for the realtime cohort")
def get_realtime_employees_status() -> list[dict]:
    return _summarise(REALTIME_MEMORY_DIR)


@router.get("/employee/{name}/briefing", summary="A person's latest briefing")
def get_employee_briefing(name: str, scope: str = "main") -> dict:
    """The manager briefing from this person's most recent evaluation."""
    name_lower = name.strip().lower()
    target_dir = memory_dir_for(scope)
    memory_files = glob.glob(os.path.join(target_dir, f"{name_lower}_week*.json"))

    if not memory_files:
        return {
            "found": False,
            "briefing": "No individual briefing card found for this employee.",
        }

    def week_of(path: str) -> int:
        stem = os.path.basename(path).replace(f"{name_lower}_week", "")
        try:
            return int(stem.replace(".json", ""))
        except ValueError:
            return 0

    try:
        with open(max(memory_files, key=week_of), encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        # CONTEXT.md rule 4: no raw error text. The correlation ID from the
        # problem+json handler is how this gets diagnosed.
        raise HTTPException(
            status_code=500, detail="That evaluation could not be read."
        ) from exc

    briefing = data.get("briefing")
    if not briefing:
        return {
            "found": False,
            "briefing": "No individual briefing card found for this employee.",
            "raw_card": "",
        }

    return {"found": True, "briefing": briefing, "raw_card": briefing}
