# Quiet Quitting Detector - Trend Detector Agent
# Role: Analyzes multi-week behavioral metrics of an employee to identify declining engagement patterns.
#       All comparisons are made against the employee's own week-1 baseline (not a global average).
#       A signal is only raised when it appears for 2 or more consecutive weeks.
#
# STRIDE fix applied (2026-06-29):
#   - [Fix 1] Session ID no longer embeds the employee first name;
#             uses a SHA-256 hash prefix instead.
#   - [Session fix] Uses run_agent_sync() which pre-creates the session
#             before calling runner.run(), avoiding SessionNotFoundError.

import hashlib
import json

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models import Gemini

from src.app_utils.names import first_name_of
from src.app_utils.runner_helper import run_agent_sync

load_dotenv(override=True)

SYSTEM_INSTRUCTION = """
You are a Quiet-Quitting Trend Detector Agent.
Your job is to analyze pre-detected disengagement signals from an employee's weekly data and
produce a clear, empathetic summary of each confirmed pattern.

You will receive a JSON list of already-detected signals. Each signal was identified by comparing
the employee's metrics against their own week-1 baseline and confirmed over 2+ consecutive weeks.

For each signal, produce a concise description of what was observed.

Strict Rules:
- Never use employee surnames or IDs in any output. Only first names are allowed.   [CONTEXT Rule 1]
- Never recommend disciplinary action -- only supportive manager responses.          [CONTEXT Rule 2]
- If a week of data is missing for an employee, note the gap -- do not assume disengagement. [CONTEXT Rule 4]
- Never expose raw Gemini API errors in the final output.                           [CONTEXT Rule 5]
- Store only behavioral signals -- never store personal opinions or health information. [CONTEXT Rule 6]

Output format:
Return a valid JSON array of objects, where each object contains:
- "signal_name": name of the signal (e.g. "Declining Task Completion")
- "weeks_detected": list of week numbers where this signal was active
- "severity": "low", "medium", or "high"
"""

# The ADK Gemini model reads GEMINI_API_KEY from env automatically
trend_detector_agent = Agent(
    name="trend_detector_agent",
    model=Gemini(model="gemini-2.5-flash"),
    instruction=SYSTEM_INSTRUCTION,
)

# ---------------------------------------------------------------------------
# Detection logic now lives in src/domain/signals.py -- pure, framework-free and
# shared by both entrypoints. This module keeps only the LLM enrichment step,
# which turns confirmed signals into supportive prose. Re-exported names below
# preserve the previous import surface for existing callers and tests.
# ---------------------------------------------------------------------------
from src.domain.models import Signal, WeekMetrics  # noqa: E402
from src.domain.protocols import TrendEnricher  # noqa: E402
from src.domain.signals import (  # noqa: E402
    AFTER_HOURS_DEVIATION,
    CONSECUTIVE_WEEKS_REQUIRED,
    HOURS_DEVIATION_PCT,
    RESPONSE_TIME_PCT,
    TASK_DROP_PCT_HIGH,
    TASK_DROP_PCT_MEDIUM,
    confirm_signals,
    find_baseline,
)

__all__ = [
    "AFTER_HOURS_DEVIATION",
    "CONSECUTIVE_WEEKS_REQUIRED",
    "HOURS_DEVIATION_PCT",
    "RESPONSE_TIME_PCT",
    "TASK_DROP_PCT_HIGH",
    "TASK_DROP_PCT_MEDIUM",
    "detect_trends",
    "trend_detector_agent",
]

#: Test/parity seam. When set, enrichment goes through this object instead of
#: the LLM. Left None in every production path -- see src/domain/protocols.py.
DEFAULT_ENRICHER: TrendEnricher | None = None


def _to_week_models(full_timeline: list[dict]) -> list[WeekMetrics]:
    """Adapt legacy dict rows to the typed domain model.

    Unknown keys are ignored by the model config, so a prohibited column left in
    a legacy CSV cannot reach the domain layer even if it survived ingest.
    """
    weeks: list[WeekMetrics] = []
    for row in full_timeline:
        week_num = row.get("week")
        if week_num is None:
            continue
        weeks.append(
            WeekMetrics(
                week=week_num,
                completed_tasks=row.get("completed_tasks"),
                response_time=row.get("response_time"),
                after_hours_logins=row.get("after_hours_logins"),
                weekly_hours=row.get("weekly_hours"),
                data_missing=bool(row.get("data_missing", False)),
            )
        )
    return weeks


def _as_dict(signal: Signal) -> dict:
    """Legacy wire format. Kept until Phase 5 moves callers onto the models."""
    row = {
        "signal_name": signal.signal_name,
        "weeks_detected": list(signal.weeks_detected),
        "severity": signal.severity.value,
    }
    if signal.details:
        row["details"] = signal.details
    return row


def detect_trends(
    employee_name: str,
    data: list[dict],
    enricher: TrendEnricher | None = None,
    cohort_shifts: dict[str, dict[int, float]] | None = None,
) -> list[dict]:
    """Analyzes the employee's multi-week data and returns confirmed signals.

    The function uses pure Python logic for deterministic signal detection, then
    optionally enriches descriptions via the LLM.  The LLM is never given
    personal identifiers beyond first name.  [CONTEXT Rule 1]
    """
    first_name = first_name_of(employee_name)  # Rule 1: First name only

    # Rule 3: Validate data exists before proceeding
    if not data:
        return []

    # Detection is delegated to src/domain/signals.py -- pure, shared, and the
    # only implementation, so the CLI and API cannot drift apart (blocker B6).
    weeks = _to_week_models(sorted(data, key=lambda w: w.get("week", 0)))

    if find_baseline(weeks) is None:
        # Rule 3: week-1 data missing -- report the gap, never infer disengagement.
        return [
            {
                "signal_name": "Baseline Week Missing",
                "weeks_detected": [],
                "severity": "low",
            }
        ]

    # Cohort shifts remove movement everybody saw that week -- an outage, a
    # holiday, a scope cut. They can only ever REMOVE a signal, never add one
    # (tested in test_domain_statistics.py), so passing them is always safe.
    confirmed_signals = confirm_signals(weeks, cohort_shifts=cohort_shifts)
    if not confirmed_signals:
        return []  # No persistent patterns detected

    raw_signals = [_as_dict(sig) for sig in confirmed_signals]

    # A deterministic enricher short-circuits the LLM entirely. This is the seam
    # that makes both entrypoints reproducible (6.3) -- no network, no retries,
    # no variance between two runs on the same fixture.
    active_enricher = enricher or DEFAULT_ENRICHER
    if active_enricher is not None:
        return [
            _as_dict(sig)
            for sig in active_enricher.enrich(first_name, confirmed_signals)
        ]

    # Enrich descriptions via the LLM agent
    prompt = (
        f"Employee first name: {first_name}\n"  # Rule 1: first name only
        f"Pre-detected signals (confirmed over 2+ consecutive weeks):\n"
        f"{json.dumps(raw_signals, indent=2)}\n\n"
        "For each signal, confirm the JSON fields and add brief, supportive context in a "
        "'details' field. Return the full JSON array."
    )

    # [Fix 1] Anonymised session ID -- first name is hashed, never plain-text.
    _hash12 = hashlib.sha256(first_name.lower().encode()).hexdigest()[:12]
    _session_id = f"session_employee_{_hash12}_trends"

    try:
        response_text = run_agent_sync(
            trend_detector_agent,
            user_id="orchestrator",
            session_id=_session_id,
            prompt=prompt,
        )

        clean_text = response_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()

        enriched = json.loads(clean_text)

        # Guarantee required fields are preserved even if LLM omits them
        for i, sig in enumerate(enriched):
            if i < len(raw_signals):
                sig.setdefault("signal_name", raw_signals[i]["signal_name"])
                sig.setdefault("weeks_detected", raw_signals[i]["weeks_detected"])
                sig.setdefault("severity", raw_signals[i]["severity"])

        return enriched

    except Exception:
        # Rule 5: Never expose raw Gemini API errors -- return raw programmatic signals
        return raw_signals
