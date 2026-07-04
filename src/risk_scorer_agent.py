# Quiet Quitting Detector - Risk Scorer Agent
# Role: Computes disengagement risk score based on trend signals and historical records.
#
# STRIDE fixes applied (2026-06-29):
#   - [Fix 1] Session IDs now use a SHA-256 hash prefix -- first names never appear in session identifiers.
#   - [Fix 2] _load_employee_history() enforces a MAX_HISTORY_WEEKS=12 lookback window (by file mtime)
#             and validates required fields in each memory record before accepting it.
#   - [Fix 3] Recurrence bonus decays after HEALTHY_DECAY_WEEKS=4 consecutive Healthy weeks.
#             A `healthy_streak` counter is stored in each memory file so recovery is tracked.
#   - [Session fix] Uses run_agent_sync() which pre-creates the session
#             before calling runner.run(), avoiding SessionNotFoundError.

import glob
import hashlib
import json
import logging
import os
import time

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models import Gemini

from src.app_utils.runner_helper import run_agent_sync

load_dotenv(override=True)

# Module-level logger -- never includes first names in messages.
logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """
You are a Quiet-Quitting Risk Scorer Agent.
Your job is to analyze the detected disengagement signals and the historical risk context of an
employee, then output a holistic risk assessment.

Score Scale:
- 1-3:  Healthy
- 4-5:  Watch
- 6-7:  At Risk
- 8-10: Silent Exit

Strict Rules:
- Never use employee surnames or IDs in any output. Only first names are allowed.   [CONTEXT Rule 1]
- Never recommend disciplinary action. Focus on supportive responses.               [CONTEXT Rule 2]
- If a week of data is missing, note the gap -- do not assume disengagement.        [CONTEXT Rule 4]
- Never expose raw Gemini API errors in the final output.                           [CONTEXT Rule 5]
- Never store or process personal opinions or health information. Behavioral signals only. [CONTEXT Rule 6]

Output format:
Return a valid JSON object with these keys:
- "score": integer 1-10 (already pre-adjusted for recurrence; reflect the value you are given)
- "classification": "Healthy", "Watch", "At Risk", or "Silent Exit"
- "rationale": brief, supportive explanation grounded in behavioral signals only
"""

risk_scorer_agent = Agent(
    name="risk_scorer_agent",
    model=Gemini(model="gemini-2.5-flash"),
    instruction=SYSTEM_INSTRUCTION,
)

# ---------------------------------------------------------------------------
# Score boundaries
# ---------------------------------------------------------------------------
WATCH_THRESHOLD = 4  # >= 4 is Watch or above
AT_RISK_THRESHOLD = 6
SILENT_EXIT_THRESHOLD = 8

# ---------------------------------------------------------------------------
# Memory / lookback configuration
# ---------------------------------------------------------------------------
# [Fix 2] Maximum number of weeks of history to load.
# Files whose mtime is older than this window are silently ignored.
MAX_HISTORY_WEEKS = 12
MAX_HISTORY_SECONDS = MAX_HISTORY_WEEKS * 7 * 24 * 3600

# [Fix 3] Number of consecutive Healthy weeks required to clear the recurrence bonus.
HEALTHY_DECAY_WEEKS = 4

# Required fields every memory record must contain (integrity check).   [Fix 2]
REQUIRED_MEMORY_FIELDS = {"score", "classification", "rationale"}

# Memory directory -- OS-agnostic join; backslash used only in write paths.
MEMORY_DIR = os.path.join("data", "memory")


# ---------------------------------------------------------------------------
# Helper: anonymised session ID                                           [Fix 1]
# ---------------------------------------------------------------------------
def _anon_session_id(first_name_lower: str, suffix: str) -> str:
    """Return a privacy-safe session ID: session_employee_{hash12}_{suffix}.

    The first name is hashed so it never appears in session stores,
    telemetry traces, or API request metadata.  [STRIDE Fix 1]
    """
    hash12 = hashlib.sha256(first_name_lower.encode()).hexdigest()[:12]
    return f"session_employee_{hash12}_{suffix}"


# ---------------------------------------------------------------------------
# Helper: classify score
# ---------------------------------------------------------------------------
def _classify(score: int) -> str:
    """Map a numeric score to the classification label."""
    if score >= SILENT_EXIT_THRESHOLD:
        return "Silent Exit"
    if score >= AT_RISK_THRESHOLD:
        return "At Risk"
    if score >= WATCH_THRESHOLD:
        return "Watch"
    return "Healthy"


# ---------------------------------------------------------------------------
# Helper: load employee history with lookback cap + integrity check       [Fix 2]
# ---------------------------------------------------------------------------
def _load_employee_history(first_name_lower: str) -> list[dict]:
    """Load previous JSON memory files for this employee, up to MAX_HISTORY_WEEKS.

    Changes vs original:
    - Only files whose mtime falls within the last MAX_HISTORY_WEEKS weeks are loaded.
    - Each loaded record is validated for required fields; corrupt/incomplete
      records are skipped with a warning log (no name in log message).
    - Silently skips unreadable files (Rule 5).
    """
    pattern = os.path.join(MEMORY_DIR, f"{first_name_lower}_week*.json")
    matched_files = glob.glob(pattern)

    now = time.time()
    cutoff = now - MAX_HISTORY_SECONDS  # [Fix 2] oldest acceptable mtime

    history: list[dict] = []
    for file_path in sorted(matched_files):
        # Rule 3: Validate the file exists and is within the lookback window.
        if not os.path.isfile(file_path):
            continue

        # [Fix 2] Ignore files older than MAX_HISTORY_WEEKS.
        try:
            file_mtime = os.path.getmtime(file_path)
        except OSError:
            continue
        if file_mtime < cutoff:
            logger.debug(
                "Memory file outside %d-week lookback window -- skipped.",
                MAX_HISTORY_WEEKS,
            )
            continue

        try:
            with open(file_path, encoding="utf-8") as fh:
                record = json.load(fh)
        except Exception:
            # Rule 5: Never surface raw errors -- silently skip corrupted files.
            logger.warning(
                "Memory file could not be parsed -- skipped. (path omitted for privacy)"
            )
            continue

        # [Fix 2] Integrity check: required fields must be present.
        missing_fields = REQUIRED_MEMORY_FIELDS - set(record.keys())
        if missing_fields:
            logger.warning(
                "Memory record missing required fields %s -- skipped.",
                missing_fields,
            )
            continue

        record["_source_file"] = file_path  # internal bookkeeping only
        history.append(record)

    return history


# ---------------------------------------------------------------------------
# Helper: recurrence bonus with decay                                     [Fix 3]
# ---------------------------------------------------------------------------
def _compute_recurrence_bonus(history: list[dict]) -> tuple[bool, int]:
    """Determine whether the recurrence bonus applies and the current healthy streak.

    The bonus (+1) is applied when >= 2 of the loaded history records are
    Watch-or-above AND the employee has NOT accumulated HEALTHY_DECAY_WEEKS
    consecutive Healthy weeks that would clear the bonus.

    Returns:
        (apply_bonus: bool, current_healthy_streak: int)
    """
    if not history:
        return False, 0

    # Walk history from newest to oldest to count the current healthy streak.
    sorted_history = list(
        history
    )  # already sorted by filename in _load_employee_history
    current_healthy_streak = 0
    for record in reversed(sorted_history):
        classification = record.get("classification", "").strip().upper()
        if classification == "HEALTHY":
            stored_streak = record.get("healthy_streak", 0)
            current_healthy_streak = max(current_healthy_streak + 1, stored_streak)
        else:
            break  # streak is broken at the first non-Healthy record from the end

    # If the employee has been Healthy for HEALTHY_DECAY_WEEKS consecutive weeks,
    # the recurrence bonus is cleared.                                    [Fix 3]
    if current_healthy_streak >= HEALTHY_DECAY_WEEKS:
        return False, current_healthy_streak

    # Count how many prior weeks were Watch-or-above.
    elevated_weeks = sum(
        1
        for r in sorted_history
        if r.get("classification", "").strip().upper()
        in {"WATCH", "AT RISK", "SILENT EXIT"}
    )
    apply_bonus = elevated_weeks >= 2
    return apply_bonus, current_healthy_streak


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def score_risk(employee_name: str, signals: list[dict], week_number: int) -> dict:
    """Calculates risk score and classification, loading history and saving current to data\\memory\\.

    Steps:
    1. Load recent memory files (<= MAX_HISTORY_WEEKS old).              [Fix 2]
    2. Compute recurrence bonus with healthy-streak decay.               [Fix 3]
    3. Ask the LLM to score the current signals.
    4. Apply the recurrence bonus on top of the LLM score (capped at 10).
    5. Save result (including healthy_streak) to data\\memory\\firstname_weekN.json.
    """
    # Rule 1: First name only -- never use full name, surname, or ID.
    first_name = employee_name.split()[0]
    first_name_lower = first_name.lower()

    # Step 1 ---------------------------------------------------------------
    history = _load_employee_history(first_name_lower)

    # Step 2 ---------------------------------------------------------------
    apply_recurrence_bonus, current_healthy_streak = _compute_recurrence_bonus(history)

    # Step 3: Build the LLM prompt -- first name only, behavioral signals only.
    prompt = f"Employee First Name: {first_name}\n"  # Rule 1: first name only
    prompt += f"Current Week: {week_number}\n"
    prompt += f"Detected Signals:\n{json.dumps(signals, indent=2)}\n\n"

    if history:
        # Summarise history without including personal data.             [Rule 6]
        history_summary = [
            {
                "week_file": os.path.basename(h["_source_file"]),
                "score": h.get("score"),
                "classification": h.get("classification"),
            }
            for h in history
        ]
        prompt += f"Historical Risk Records ({len(history)} week(s) within {MAX_HISTORY_WEEKS}-week window):\n"
        prompt += json.dumps(history_summary, indent=2) + "\n"
        if apply_recurrence_bonus:
            prompt += (
                "Note: A recurrence adjustment of +1 will be applied to your score "
                "post-evaluation because this employee has been Watch or above for "
                "2 or more recent weeks without a recovery streak.\n"
            )
        if current_healthy_streak > 0:
            prompt += f"Current consecutive Healthy weeks: {current_healthy_streak}\n"
    else:
        prompt += "Historical Risk Records: No previous weeks on record.\n"

    prompt += "\nEvaluate the risk of disengagement and return the JSON object."

    try:
        response_text = run_agent_sync(
            risk_scorer_agent,
            user_id="orchestrator",
            # [Fix 1] Anonymised session ID -- first name is hashed, never plain-text.
            session_id=_anon_session_id(first_name_lower, "risk"),
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

        result = json.loads(clean_text)

        # Step 4: Apply recurrence bonus (+1), capped at 10.            [Fix 3]
        if apply_recurrence_bonus:
            original_score = int(result.get("score", 1))
            adjusted_score = min(original_score + 1, 10)
            result["score"] = adjusted_score
            result["classification"] = _classify(adjusted_score)
            result["rationale"] = (
                result.get("rationale", "")
                + f" [Recurrence adjustment applied: score increased from "
                f"{original_score} to {adjusted_score}.]"
            )

        # Step 5: Determine the new healthy streak for this week.       [Fix 3]
        is_now_healthy = result.get("classification", "").strip().upper() == "HEALTHY"
        new_healthy_streak = (current_healthy_streak + 1) if is_now_healthy else 0
        result["healthy_streak"] = new_healthy_streak  # stored in memory JSON

        # Save to memory ----------------------------------------------------
        os.makedirs(MEMORY_DIR, exist_ok=True)  # Rule 3: ensure dir exists
        memory_file_name = f"{first_name_lower}_week{week_number}.json"
        current_file_path = (
            MEMORY_DIR + "\\" + memory_file_name
        )  # Windows backslash path

        # Strip internal bookkeeping key before saving.          [Rule 6]
        save_result = {k: v for k, v in result.items() if not k.startswith("_")}
        save_result["signals"] = signals
        with open(current_file_path, "w", encoding="utf-8") as fh:
            json.dump(save_result, fh, indent=2)

        return save_result

    except Exception:
        # Rule 5: Never expose raw Gemini API errors -- return a safe fallback.
        fallback = {
            "score": 4,
            "classification": "Watch",
            "rationale": (
                "Evaluation could not be fully completed due to a temporary service error. "
                "Defaulted to Watch classification for safety."
            ),
            "healthy_streak": 0,
            "signals": signals,
        }

        # Still attempt to save the fallback so history remains continuous.
        try:
            os.makedirs(MEMORY_DIR, exist_ok=True)
            memory_file_name = f"{first_name_lower}_week{week_number}.json"
            fallback_path = MEMORY_DIR + "\\" + memory_file_name
            with open(fallback_path, "w", encoding="utf-8") as fh:
                json.dump(fallback, fh, indent=2)
        except Exception:
            pass  # Rule 5: suppress secondary errors silently

        return fallback
