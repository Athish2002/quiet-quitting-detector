# Quiet Quitting Detector - Trend Detector Agent
# Role: Analyzes multi-week behavioral metrics of an employee to identify declining engagement patterns.
#       All comparisons are made against the employee's own week-1 baseline (not a global average).
#       A signal is only raised when it appears for 2 or more consecutive weeks.
#
# STRIDE fix applied (2026-06-29):
#   - [Fix 1] Session ID no longer embeds the employee first name;
#             uses a SHA-256 hash prefix instead.

import hashlib
import json

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models import Gemini
from google.adk.runners import InMemoryRunner
from google.genai import types

load_dotenv()

SYSTEM_INSTRUCTION = """
You are a Quiet-Quitting Trend Detector Agent.
Your job is to analyze pre-detected disengagement signals from an employee's weekly data and
produce a clear, empathetic summary of each confirmed pattern.

You will receive a JSON list of already-detected signals. Each signal was identified by comparing
the employee's metrics against their own week-1 baseline and confirmed over 2+ consecutive weeks.

For each signal, produce a concise description of what was observed.

Strict Rules:
- Never use employee surnames or IDs in any output. Only first names are allowed.   [CONTEXT Rule 1]
- Never recommend disciplinary action — only supportive manager responses.          [CONTEXT Rule 2]
- If a week of data is missing for an employee, note the gap — do not assume disengagement. [CONTEXT Rule 4]
- Never expose raw Gemini API errors in the final output.                           [CONTEXT Rule 5]
- Store only behavioral signals — never store personal opinions or health information. [CONTEXT Rule 6]

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
# Thresholds used for programmatic signal detection
# ---------------------------------------------------------------------------
TASK_DROP_PCT_MEDIUM = 0.20  # >= 20% drop from baseline → medium severity
TASK_DROP_PCT_HIGH = 0.40  # >= 40% drop from baseline → high severity
RESPONSE_TIME_PCT = 0.50  # > 50% increase from baseline → signal
AFTER_HOURS_THRESHOLD = 2  # > 2 after-hours logins in a week → signal
SICK_DAY_INCREASE = 1  # any increase above baseline in the last 2 weeks


def _get_baseline(full_timeline: list[dict]) -> dict | None:
    """Return the week-1 record, or None if it is missing/null.

    Rule 4: If week 1 data is missing we cannot baseline — handled by caller.
    """
    for week in full_timeline:
        if week.get("week") == 1 and not week.get("data_missing"):
            return week
    return None


def _detect_raw_flags(
    full_timeline: list[dict], baseline: dict
) -> dict[int, list[str]]:
    """Return a mapping of {week_number: [signal_names_active_that_week]}.

    Comparisons are always against the employee's own week-1 baseline, not a
    global average.  [CONTEXT Rule 3 — validate data exists before reading]
    """
    week_flags: dict[int, list[str]] = {}

    baseline_tasks = baseline.get("completed_tasks")
    baseline_response = baseline.get("response_time")
    baseline_sick = baseline.get("sick_days")

    for week in full_timeline:
        week_num = week.get("week")
        if week.get("data_missing") or week_num == 1:
            # Rule 4: Missing data is a gap, not disengagement — skip silently
            week_flags[week_num] = []
            continue

        flags: list[str] = []

        # --- Signal 1: Declining Task Completion ---
        tasks = week.get("completed_tasks")
        if tasks is not None and baseline_tasks is not None and baseline_tasks > 0:
            drop_pct = (baseline_tasks - tasks) / baseline_tasks
            if drop_pct >= TASK_DROP_PCT_MEDIUM:  # 20 %+ drop vs own baseline
                flags.append("Declining Task Completion")

        # --- Signal 2: Response Time Spike ---
        resp = week.get("response_time")
        if resp is not None and baseline_response is not None and baseline_response > 0:
            increase_pct = (resp - baseline_response) / baseline_response
            if increase_pct > RESPONSE_TIME_PCT:  # > 50 % above own baseline
                flags.append("Response Time Spike")

        # --- Signal 3: Excessive After-Hours Logins ---
        after_hours = week.get("after_hours_logins")
        if after_hours is not None and after_hours > AFTER_HOURS_THRESHOLD:
            flags.append("Excessive After-Hours Logins")

        # --- Signal 4: Increasing Sick Days ---
        sick = week.get("sick_days")
        if sick is not None and baseline_sick is not None:
            if sick > baseline_sick + SICK_DAY_INCREASE:  # risen above own baseline
                flags.append("Increasing Sick Days")

        week_flags[week_num] = flags

    return week_flags


def _require_consecutive(
    week_flags: dict[int, list[str]], all_weeks: list[int]
) -> dict[str, list[int]]:
    """Keep only signals that appear in 2 or more CONSECUTIVE weeks.

    A single bad week is not a pattern.
    Returns {signal_name: [week_numbers_where_active]}.
    """
    # Collect every unique signal name observed
    all_signal_names: set[str] = set()
    for flags in week_flags.values():
        all_signal_names.update(flags)

    confirmed: dict[str, list[int]] = {}

    for signal in all_signal_names:
        # Build the ordered list of weeks where this signal fired
        active_weeks = sorted(w for w, flags in week_flags.items() if signal in flags)

        # Find consecutive runs of length >= 2
        confirmed_weeks: list[int] = []
        i = 0
        while i < len(active_weeks):
            # Start a run from active_weeks[i]
            run = [active_weeks[i]]
            j = i + 1
            while j < len(active_weeks) and active_weeks[j] == active_weeks[j - 1] + 1:
                run.append(active_weeks[j])
                j += 1
            if len(run) >= 2:  # Only a pattern if 2+ consecutive weeks
                confirmed_weeks.extend(run)
            i = j

        if confirmed_weeks:
            confirmed[signal] = sorted(set(confirmed_weeks))

    return confirmed


def _assign_severity(
    signal_name: str,
    weeks_detected: list[int],
    full_timeline: list[dict],
    baseline: dict,
) -> str:
    """Assign a severity level based on the magnitude of the worst week observed."""
    if signal_name == "Declining Task Completion":
        baseline_tasks = baseline.get("completed_tasks") or 0
        worst_drop = 0.0
        for week in full_timeline:
            if week.get("week") in weeks_detected and not week.get("data_missing"):
                tasks = week.get("completed_tasks")
                if tasks is not None and baseline_tasks > 0:
                    drop = (baseline_tasks - tasks) / baseline_tasks
                    worst_drop = max(worst_drop, drop)
        if worst_drop >= TASK_DROP_PCT_HIGH:
            return "high"
        elif worst_drop >= TASK_DROP_PCT_MEDIUM:
            return "medium"
        return "low"

    if signal_name == "Response Time Spike":
        baseline_resp = baseline.get("response_time") or 0.0
        worst_increase = 0.0
        for week in full_timeline:
            if week.get("week") in weeks_detected and not week.get("data_missing"):
                resp = week.get("response_time")
                if resp is not None and baseline_resp > 0:
                    inc = (resp - baseline_resp) / baseline_resp
                    worst_increase = max(worst_increase, inc)
        if worst_increase >= 1.0:  # 100 %+ increase
            return "high"
        elif worst_increase >= 0.5:  # 50-99 %
            return "medium"
        return "low"

    if signal_name == "Excessive After-Hours Logins":
        worst = max(
            (w.get("after_hours_logins") or 0)
            for w in full_timeline
            if w.get("week") in weeks_detected
        )
        return "high" if worst >= 6 else "medium" if worst >= 4 else "low"

    if signal_name == "Increasing Sick Days":
        baseline_sick = baseline.get("sick_days") or 0
        worst = max(
            (w.get("sick_days") or 0)
            for w in full_timeline
            if w.get("week") in weeks_detected
        )
        diff = worst - baseline_sick
        return "high" if diff >= 3 else "medium" if diff >= 2 else "low"

    return "medium"  # fallback


def detect_trends(employee_name: str, data: list[dict]) -> list[dict]:
    """Analyzes the employee's multi-week data and returns confirmed signals.

    The function uses pure Python logic for deterministic signal detection, then
    optionally enriches descriptions via the LLM.  The LLM is never given
    personal identifiers beyond first name.  [CONTEXT Rule 1]
    """
    first_name = employee_name.split()[0]  # Rule 1: First name only

    # Rule 3: Validate data exists before proceeding
    if not data:
        return []

    # Sort chronologically
    full_timeline = sorted(data, key=lambda w: w.get("week", 0))
    all_weeks = [w["week"] for w in full_timeline]

    # Establish the week-1 baseline for this specific employee
    baseline = _get_baseline(full_timeline)
    if baseline is None:
        # Rule 4: Week-1 data is missing — note gap, do not assume disengagement
        return [
            {
                "signal_name": "Baseline Week Missing",
                "weeks_detected": [],
                "severity": "low",
            }
        ]

    # Detect which signals fired each week
    week_flags = _detect_raw_flags(full_timeline, baseline)

    # Keep only signals active for 2+ consecutive weeks — single bad week is not a pattern
    confirmed = _require_consecutive(week_flags, all_weeks)

    if not confirmed:
        return []  # No persistent patterns detected

    # Build structured output list
    raw_signals = []
    for signal_name, weeks_detected in confirmed.items():
        severity = _assign_severity(
            signal_name, weeks_detected, full_timeline, baseline
        )
        raw_signals.append(
            {
                "signal_name": signal_name,
                "weeks_detected": weeks_detected,
                "severity": severity,
            }
        )

    # Enrich descriptions via the LLM agent
    prompt = (
        f"Employee first name: {first_name}\n"  # Rule 1: first name only
        f"Pre-detected signals (confirmed over 2+ consecutive weeks):\n"
        f"{json.dumps(raw_signals, indent=2)}\n\n"
        "For each signal, confirm the JSON fields and add brief, supportive context in a "
        "'details' field. Return the full JSON array."
    )

    runner = InMemoryRunner(agent=trend_detector_agent)

    # [Fix 1] Anonymised session ID — first name is hashed, never plain-text.
    _hash12 = hashlib.sha256(first_name.lower().encode()).hexdigest()[:12]
    _session_id = f"session_employee_{_hash12}_trends"

    try:
        events = list(
            runner.run(
                user_id="orchestrator",
                session_id=_session_id,
                new_message=types.Content(
                    role="user", parts=[types.Part.from_text(text=prompt)]
                ),
            )
        )

        response_text = ""
        for event in events:
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        response_text += part.text

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
        # Rule 5: Never expose raw Gemini API errors — return raw programmatic signals
        return raw_signals
