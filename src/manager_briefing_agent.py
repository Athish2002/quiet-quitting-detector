# Quiet Quitting Detector - Manager Briefing Agent
# Role: Generates supportive and HR-safe briefings for managers of flagged employees.
#
# STRIDE fixes applied (2026-06-29):
#   - [Fix 1] Session ID no longer embeds the employee first name;
#             uses a SHA-256 hash prefix instead.
#   - [Fix 1] Error fallback string no longer includes the first name.
#   - [Fix 4] Output validator added: briefings containing unsafe phrases,
#             raw error markers, or API error patterns are replaced with a
#             safe fallback before being returned.
#   - [Session fix] Uses run_agent_sync() which pre-creates the session
#             before calling runner.run(), avoiding SessionNotFoundError.

import hashlib
import logging
import re

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models import Gemini

from src.app_utils.runner_helper import run_agent_sync

load_dotenv(override=True)

# Module-level logger -- never includes first names.
logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """
You are a Supportive Manager Briefing Agent.
Your job is to generate supportive, constructive, and HR-safe briefing documents for managers whose team members show signs of disengagement (Watch, At Risk, Silent Exit).

Strict Guidelines you must enforce:
1. Privacy: Never use employee surnames or IDs in any output. Only first names are allowed.
2. Tone: Keep the tone warm, constructive, empathetic, and supportive. Never make it accusatory or punitive.
3. No Disciplinary Action: Never recommend disciplinary or negative action. Focus on how the manager can support the employee's well-being and engagement.
4. Gaps: If a week of data is missing, note the gap and explicitly mention that it should not be assumed as disengagement.
5. Personal Information: Never mention or store personal opinions, health issues, or non-behavioral personal details.
6. Error Safety: Never expose raw Gemini API errors in the final output.

Your briefing output MUST contain ALL of the following clearly labelled sections:
- "Signals Detected": A brief explanation of the behavioral patterns identified.
- "Pre-Meeting Observation": Suggestions on what the manager can observe before the 1-on-1.
- "3 Supportive Things to Say": Actionable, warm questions or statements to use.
- "2 Things Never to Say": Accusatory or demotivating statements to avoid.
- "Evidence-Based Actions": For At Risk and Silent Exit employees, include 2-3 concrete, supportive actions the manager can take this week (e.g. schedule a 1-on-1, offer workload adjustment, connect to wellbeing resources).
"""

manager_briefing_agent = Agent(
    name="manager_briefing_agent",
    model=Gemini(model="gemini-2.5-flash"),
    instruction=SYSTEM_INSTRUCTION,
)

# ---------------------------------------------------------------------------
# [Fix 4] Output validator deny-list
# ---------------------------------------------------------------------------
# These patterns indicate unsafe, punitive, or erroneous content.
# Matching is case-insensitive.
_UNSAFE_PATTERNS: list[re.Pattern] = [
    re.compile(r"performance improvement plan", re.IGNORECASE),
    re.compile(r"\bdisciplinar(y|ied|ies)\b", re.IGNORECASE),
    re.compile(r"\bmonitor(ed|ing|s)?\b.*\bactivity\b", re.IGNORECASE),
    re.compile(r"\bsurveillance\b", re.IGNORECASE),
    re.compile(r"\bterminate\b|\btermination\b", re.IGNORECASE),
    re.compile(r"\bconsequence[s]?\b", re.IGNORECASE),
    re.compile(r"\bwarning letter\b", re.IGNORECASE),
    # Raw error markers -- catches API/runtime errors leaking through
    re.compile(r"^Error:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Exception:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"Traceback \(most recent call last\)", re.IGNORECASE),
    re.compile(r"google\.api_core\.exceptions\.", re.IGNORECASE),
]

_SAFE_FALLBACK_BRIEFING = (
    "Manager Briefing:\n"
    "A temporary issue prevented a detailed briefing from being generated. "
    "Please conduct the next 1-on-1 using open, supportive questions -- for example: "
    "'How are you finding your current workload?' or 'Is there anything I can do to "
    "better support you right now?' Focus on listening and removing obstacles rather "
    "than drawing conclusions from metrics alone."
)


def _anon_session_id(first_name_lower: str, suffix: str) -> str:
    """Return a privacy-safe session ID: session_employee_{hash12}_{suffix}.

    The first name is hashed so it never appears in session stores,
    telemetry traces, or API request metadata.  [STRIDE Fix 1]
    """
    hash12 = hashlib.sha256(first_name_lower.encode()).hexdigest()[:12]
    return f"session_employee_{hash12}_{suffix}"


def _validate_briefing(text: str) -> str:
    """[Fix 4] Scan the generated briefing for unsafe or erroneous content.

    If any deny-listed pattern is found, the text is replaced with
    _SAFE_FALLBACK_BRIEFING and a warning is emitted to the logger
    (without including the employee name).
    """
    for pattern in _UNSAFE_PATTERNS:
        if pattern.search(text):
            logger.warning(
                "Briefing output validator blocked unsafe content "
                "(pattern: %s). Returning safe fallback.",
                pattern.pattern,
            )
            return _SAFE_FALLBACK_BRIEFING
    return text


def generate_briefing(employee_name: str, signals: list[dict], risk_data: dict) -> str:
    """Generates a warm, supportive briefing for the manager if classification is Watch, At Risk, or Silent Exit."""
    classification = risk_data.get("classification", "").upper()
    if classification not in ["WATCH", "AT RISK", "SILENT EXIT"]:
        return ""  # Do not run for Healthy employees

    first_name = employee_name.split()[0]

    prompt = f"Create a manager briefing for employee: {first_name}\n"
    prompt += f"Risk Category: {risk_data.get('classification')} (Score: {risk_data.get('score')}/10)\n"
    prompt += f"Risk Rationale: {risk_data.get('rationale')}\n"
    prompt += "Behavioral Signals Detected:\n"
    for s in signals:
        prompt += f"- {s.get('signal_name') or s.get('signal')} (Severity: {s.get('severity')}): {s.get('details', '')}\n"

    try:
        response_text = run_agent_sync(
            manager_briefing_agent,
            user_id="orchestrator",
            # [Fix 1] Anonymised session ID -- first name is hashed, never plain-text.
            session_id=_anon_session_id(first_name.lower(), "briefing"),
            prompt=prompt,
        )

        # [Fix 4] Validate output before returning it.
        return _validate_briefing(response_text)

    except Exception:
        # Rule 5: Never expose raw Gemini API errors.
        # [Fix 1] Error fallback no longer embeds the first name.
        return _SAFE_FALLBACK_BRIEFING
