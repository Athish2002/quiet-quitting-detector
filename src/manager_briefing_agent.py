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

from src.app_utils.names import first_name_of
from src.app_utils.runner_helper import run_agent_sync
from src.domain.critique import Critique, critique_briefing
from src.domain.models import Confidence

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
7. Forbidden Terms: Do NOT write or output terms like "disciplinary", "disciplinary action", "performance improvement plan", "PIP", "termination", "surveillance", "consequence", "consequences", or "warning letter" anywhere in your text. Even when writing the 'Things Never to Say' section, avoid using these words. Instead of saying "Never threaten disciplinary action", write "Never threaten formal review or negative feedback."
8. Personalization: Make the questions and observations deeply unique to the person's specific behavioral patterns (e.g. late evening work, cognitive overload, response latency, or workflow friction). Never use repetitive or generic templates.

Your briefing output MUST contain ALL of the following clearly labelled sections:
- "Signals Detected": A brief explanation of the behavioral patterns identified.
- "Pre-Meeting Observation": Suggestions on what the manager can observe before the 1-on-1.
- "3 Supportive Things to Say": Actionable, warm, deeply personalized questions or statements tailored to this specific person.
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


def _predict_local_briefing_fallback(
    current_signals: list[dict], memory_dir: str
) -> str | None:
    """Finds the most similar historical evaluation and returns its briefing card
    as an ML-driven fallback when APIs are offline.
    """
    import glob
    import json
    import os

    current_signal_names = {
        s.get("signal_name") for s in current_signals if s.get("signal_name")
    }

    best_similarity = -1.0
    best_briefing = None

    pattern = os.path.join(memory_dir, "*.json")
    for file_path in glob.glob(pattern):
        try:
            with open(file_path, encoding="utf-8") as fh:
                hist_data = json.load(fh)

            hist_briefing = hist_data.get("briefing", "")
            if (
                not hist_briefing
                or "A temporary issue prevented a detailed briefing" in hist_briefing
            ):
                continue

            hist_signals = {
                s.get("signal_name")
                for s in hist_data.get("signals", [])
                if s.get("signal_name")
            }

            intersection = current_signal_names.intersection(hist_signals)
            union = current_signal_names.union(hist_signals)
            similarity = len(intersection) / len(union) if union else 1.0

            if similarity > best_similarity:
                best_similarity = similarity
                best_briefing = (
                    f"[Local ML Fallback Briefing] (Matched {int(similarity * 100)}% similarity to "
                    f"historical behavioral patterns)\n\n" + hist_briefing
                )
        except Exception:
            continue

    if best_briefing and best_similarity >= 0.5:
        return best_briefing
    return None


#: How many revision attempts the critic gets before falling back to safe text.
#: One. If the model could not fix a named, specific problem on the first try, a
#: second identical nudge is unlikely to help and every extra attempt is another
#: API call spent on a briefing that is already suspect.
MAX_REVISIONS = 1


def _signal_names(signals: list[dict]) -> list[str]:
    names = []
    for signal in signals:
        name = signal.get("signal_name") or signal.get("signal")
        if name:
            names.append(str(name))
    return names


def _run_critique(
    text: str,
    first_name: str,
    signals: list[dict],
    risk_data: dict,
) -> Critique:
    """Check a draft against the six rules and the evidence actually available."""
    try:
        confidence = Confidence(str(risk_data.get("confidence", "moderate")).lower())
    except ValueError:
        confidence = Confidence.MODERATE

    return critique_briefing(
        text,
        first_name=first_name,
        confirmed_signals=_signal_names(signals),
        confidence=confidence,
        has_data_gap=any(
            (s.get("signal") or s.get("signal_name")) == "MISSING_DATA_GAP"
            for s in signals
        ),
    )


def generate_briefing(
    employee_name: str,
    signals: list[dict],
    risk_data: dict,
    memory_dir: str | None = None,
    continuity: str = "",
) -> str:
    """Generates a warm, supportive briefing for the manager if classification is Watch, At Risk, or Silent Exit.

    Phase 3 adds two things around the draft:

    * `continuity` -- what happened in prior weeks and what the manager said
      back, so week 8 builds on week 3 instead of restarting from zero (6.2).
    * a self-critique pass -- the draft is checked against the six ethical rules
      AND against the signals actually confirmed, then revised once if needed.
      The regex validator below is now the last line of defence rather than the
      only one: it can catch a banned word, but not a briefing that states a
      conclusion the evidence never supported.
    """
    classification = risk_data.get("classification", "").upper()
    if classification not in ["WATCH", "AT RISK", "SILENT EXIT"]:
        return ""  # Do not run for Healthy employees

    first_name = first_name_of(employee_name)

    prompt = f"Create a manager briefing for employee: {first_name}\n"
    prompt += f"Risk Category: {risk_data.get('classification')} (Score: {risk_data.get('score')}/10)\n"
    prompt += f"Risk Rationale: {risk_data.get('rationale')}\n"

    confidence = str(risk_data.get("confidence", "")).lower()
    if confidence in ("low", "none"):
        prompt += (
            "CONFIDENCE IS LOW. There is not yet enough of this person's own "
            "history to be sure. Write the briefing as a question worth asking, "
            "not as a finding. Say plainly that the evidence is thin.\n"
        )

    if continuity:
        prompt += (
            "\nContinuity from previous weeks (behavioural only -- build on this, "
            f"do not restart from zero):\n{continuity}\n"
        )

    prompt += "\nBehavioral Signals Detected:\n"
    for s in signals:
        prompt += f"- {s.get('signal_name') or s.get('signal')} (Severity: {s.get('severity')}): {s.get('details', '')}\n"

    prompt += (
        "\nDiscuss ONLY the signals listed above. Do not introduce any other "
        "pattern, and do not describe what the person feels, wants, or intends.\n"
    )

    try:
        response_text = run_agent_sync(
            manager_briefing_agent,
            user_id="orchestrator",
            # [Fix 1] Anonymised session ID -- first name is hashed, never plain-text.
            session_id=_anon_session_id(first_name.lower(), "briefing"),
            prompt=prompt,
        )

        # Phase 3: critique, then revise once if the critic found something.
        for _ in range(MAX_REVISIONS):
            critique = _run_critique(response_text, first_name, signals, risk_data)
            if critique.is_clean:
                break

            logger.info(
                "Briefing critique found %d issue(s); requesting one revision.",
                len(critique.findings),
            )
            response_text = run_agent_sync(
                manager_briefing_agent,
                user_id="orchestrator",
                session_id=_anon_session_id(first_name.lower(), "briefing-revise"),
                prompt=(
                    f"{prompt}\n\nYour previous draft:\n{response_text}\n\n"
                    f"{critique.revision_instructions()}\n"
                    "Return the corrected briefing only."
                ),
            )

        # A blocking finding that survived the revision is not delivered. These
        # map onto CONTEXT.md rules, and a rule violation is not a quality
        # trade-off to be weighed against the briefing being useful.
        final_critique = _run_critique(response_text, first_name, signals, risk_data)
        if final_critique.must_block:
            logger.warning(
                "Briefing blocked by critic after revision: %s",
                [f.value for f in final_critique.findings],
            )
            return _SAFE_FALLBACK_BRIEFING

        # [Fix 4] Validate output before returning it.
        return _validate_briefing(response_text)

    except Exception:
        # Rule 5: Never expose raw Gemini API errors -- attempt Local ML prediction
        if memory_dir:
            matched_briefing = _predict_local_briefing_fallback(signals, memory_dir)
            if matched_briefing:
                return matched_briefing
        # [Fix 1] Error fallback no longer embeds the first name.
        return _SAFE_FALLBACK_BRIEFING
