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
import re
import time

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models import Gemini

from src.app_utils.names import first_name_of
from src.app_utils.runner_helper import run_agent_sync
from src.domain.models import HistoryRecord, Severity, Signal, WeekMetrics
from src.domain.protocols import RiskScorer
from src.domain.risk import (
    AT_RISK_THRESHOLD,
    HEALTHY_DECAY_WEEKS,
    SILENT_EXIT_THRESHOLD,
    WATCH_THRESHOLD,
    apply_recurrence_bonus,
    next_healthy_streak,
)
from src.domain.risk import classify as _classify
from src.domain.risk import compute_recurrence_bonus as _domain_recurrence

# Re-exported for backwards compatibility: these bands lived here before the
# domain extraction and external callers may still import them from this module.
__all__ = [
    "AT_RISK_THRESHOLD",
    "HEALTHY_DECAY_WEEKS",
    "SILENT_EXIT_THRESHOLD",
    "WATCH_THRESHOLD",
    "risk_scorer_agent",
    "score_risk",
]

load_dotenv(override=True)

# Module-level logger -- never includes first names in messages.
logger = logging.getLogger(__name__)

#: Test/parity seam. When set, scoring goes through this object instead of the
#: LLM. Left None in every production path -- see src/domain/protocols.py.
DEFAULT_SCORER: RiskScorer | None = None

#: Pseudo-signal the orchestrator appends when a week's data is absent. It must
#: never contribute to risk (CONTEXT.md rule 3: a gap is a gap, not evidence),
#: so it is carried as wellbeing-only and the risk index ignores it.
MISSING_DATA_SIGNAL = "MISSING_DATA_GAP"

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
# Score bands, recurrence decay and classification now live in
# src/domain/risk.py -- pure and shared. Re-exported here so existing imports
# and tests keep working unchanged.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Memory / lookback configuration
# ---------------------------------------------------------------------------
# [Fix 2] Maximum number of weeks of history to load.
# Files whose mtime is older than this window are silently ignored.
MAX_HISTORY_WEEKS = 12
MAX_HISTORY_SECONDS = MAX_HISTORY_WEEKS * 7 * 24 * 3600

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
# Helper: load employee history with lookback cap + integrity check       [Fix 2]
# ---------------------------------------------------------------------------
_WEEK_FILE_RE = re.compile(r"_week(\d+)\.json$", re.IGNORECASE)


def _week_num_from_path(file_path: str) -> int | None:
    """Extract the week number embedded in a `{name}_week{N}.json` filename."""
    match = _WEEK_FILE_RE.search(os.path.basename(file_path))
    return int(match.group(1)) if match else None


def _load_employee_history(
    first_name_lower: str,
    memory_dir: str | None = None,
    before_week: int | None = None,
) -> list[dict]:
    """Load previous JSON memory files for this employee, up to MAX_HISTORY_WEEKS.

    Changes vs original:
    - Only files whose mtime falls within the last MAX_HISTORY_WEEKS weeks are loaded.
    - [Fix 5] Only files for weeks strictly before `before_week` are loaded, and the
      result is ordered by that week number (not filename string, which sorts
      "week10" before "week2"). Without this cap, re-running the chronological
      simulation (run_pipeline.py) without clearing data/memory/ first lets a
      week-1 evaluation see leftover week-3/4 files from a prior run.
    - Each loaded record is validated for required fields; corrupt/incomplete
      records are skipped with a warning log (no name in log message).
    - Silently skips unreadable files (Rule 5).
    """
    local_dir = memory_dir or MEMORY_DIR
    pattern = os.path.join(local_dir, f"{first_name_lower}_week*.json")
    matched_files = glob.glob(pattern)

    now = time.time()
    cutoff = now - MAX_HISTORY_SECONDS  # [Fix 2] oldest acceptable mtime

    dated_files: list[tuple[int, str]] = []
    for file_path in matched_files:
        week_num = _week_num_from_path(file_path)
        if week_num is None:
            continue
        if before_week is not None and week_num >= before_week:
            # [Fix 5] Never let a week's evaluation see a later week's file.
            continue
        dated_files.append((week_num, file_path))

    # [Fix 5] Chronological order by week number, not filename string.
    dated_files.sort(key=lambda pair: pair[0])

    history: list[dict] = []
    for _week_num, file_path in dated_files:
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
    """Adapter over the pure domain rule. Kept for the existing call sites.

    Records that fail validation are skipped rather than crashing the scorer --
    a corrupt memory file must not stop an evaluation.
    """
    return _domain_recurrence(_to_history_models(history))


def _to_signal_models(signals: list[dict]) -> list[Signal]:
    """Adapt the legacy signal dicts to typed models for a Protocol scorer.

    Two shapes exist on the wire: detector output keyed `signal_name`, and the
    orchestrator's gap marker keyed `signal`. Unparseable entries are dropped
    rather than guessed at -- inventing a signal is the one failure mode this
    system must not have.
    """
    models: list[Signal] = []
    for raw in signals:
        name = raw.get("signal_name") or raw.get("signal")
        if not name:
            continue
        try:
            severity = Severity(str(raw.get("severity", "medium")).lower())
        except ValueError:
            severity = Severity.MEDIUM
        weeks = raw.get("weeks_detected") or []
        models.append(
            Signal(
                signal_name=str(name),
                weeks_detected=tuple(int(w) for w in weeks if isinstance(w, int)),
                severity=severity,
                wellbeing_only=str(name) == MISSING_DATA_SIGNAL,
                details=str(raw.get("details", "")),
            )
        )
    return models


def _active_model_version() -> str:
    """Which scoring model is currently live.

    Imported lazily and failure-tolerant on purpose: an unreadable registry must
    degrade to "we do not know which model this was" rather than take down
    scoring. An unattributable prediction is a real cost, but a pipeline that
    stops because a pointer file is missing is a worse one.
    """
    try:
        from src.evolution.registry import ModelRegistry

        return ModelRegistry().active_version()
    except Exception:
        logger.warning("Could not read the active model version.")
        return "unknown"


def _to_week_models(timeline: list[dict]) -> list[WeekMetrics]:
    """Adapt legacy timeline rows so a scorer can judge how much evidence exists.

    Shared shape with the trend detector's adapter; both drop unknown keys, so a
    prohibited column surviving in a legacy CSV still cannot reach the domain.
    """
    weeks: list[WeekMetrics] = []
    for row in timeline:
        if row.get("week") is None:
            continue
        try:
            weeks.append(WeekMetrics.model_validate(row))
        except Exception:
            logger.warning("Skipping malformed timeline row.")
    return weeks


def _to_history_models(history: list[dict]) -> list[HistoryRecord]:
    """Same tolerant adaptation for stored weeks. Malformed records are skipped."""
    records: list[HistoryRecord] = []
    for raw in history:
        try:
            records.append(HistoryRecord.model_validate(raw))
        except Exception:
            logger.warning("Skipping malformed history record.")
    return records


def _nearest_neighbor_fallback(
    current_signals: list[dict], memory_dir: str
) -> dict | None:
    """Jaccard-similarity nearest-neighbor match against historical records.

    Used when there isn't yet enough historical data to train the local
    regression model (see `_predict_local_ml_fallback`). Returns None if no
    sufficiently similar historical record exists (similarity < 0.5).
    """
    import glob

    current_signal_names = {
        s.get("signal_name") for s in current_signals if s.get("signal_name")
    }

    best_match_file = None
    best_similarity = -1.0
    best_record = None

    pattern = os.path.join(memory_dir, "*.json")
    for file_path in glob.glob(pattern):
        try:
            with open(file_path, encoding="utf-8") as fh:
                hist_data = json.load(fh)

            # Skip fallback records themselves to avoid self-reinforcing default Watch loops
            rationale = hist_data.get("rationale", "")
            if "Fallback Model]" in rationale or "Local ML Fallback" in rationale:
                continue

            hist_signals = {
                s.get("signal_name")
                for s in hist_data.get("signals", [])
                if s.get("signal_name")
            }

            # Calculate Jaccard Similarity (intersection over union of signal sets)
            intersection = current_signal_names.intersection(hist_signals)
            union = current_signal_names.union(hist_signals)

            similarity = len(intersection) / len(union) if union else 1.0

            if similarity > best_similarity:
                best_similarity = similarity
                best_match_file = file_path
                best_record = hist_data
        except Exception:
            continue

    if best_record and best_match_file and best_similarity >= 0.5:
        logger.info(
            "Nearest-neighbor fallback: matched historical record from %s with similarity %.2f",
            os.path.basename(best_match_file),
            best_similarity,
        )
        return {
            "score": best_record.get("score", 4),
            "classification": best_record.get("classification", "Watch"),
            "rationale": (
                f"[Local Nearest-Neighbor Fallback] Classified with {int(best_similarity * 100)}% "
                f"signal similarity based on historical behavioral patterns. "
                f"Reference Rationale: {best_record.get('rationale', '')}"
            ),
            "healthy_streak": 0,
            "signals": current_signals,
        }

    return None


def _predict_local_ml_fallback(current_signals: list[dict], memory_dir: str) -> dict:
    """Predicts score and classification locally when all LLM APIs are
    offline/rate-limited, in three progressively-degrading tiers:

    1. A scikit-learn regression model trained on-the-fly from this
       project's own historical data/memory/*.json records (gets smarter
       as more real weeks accumulate).
    2. A Jaccard-similarity nearest-neighbor match against historical
       records, if there isn't yet enough data to train tier 1.
    3. A hardcoded Watch/4 default, if there is no usable history at all.
    """
    from src.app_utils.local_ml import train_local_model

    model = train_local_model(memory_dir)
    if model is not None:
        try:
            predicted_score = model.predict_score(current_signals)
            score = max(1, min(10, round(predicted_score)))
            classification = _classify(score)
            logger.info(
                "Local ML model: predicted score %.2f (rounded %d) from %d training samples.",
                predicted_score,
                score,
                model.sample_count,
            )
            return {
                "score": score,
                "classification": classification,
                "rationale": (
                    f"[Local ML Fallback Model] A locally-trained regression model "
                    f"(learned from {model.sample_count} prior evaluation(s) stored in "
                    f"this project's own history) predicted a risk score of {score}/10 "
                    f"from the current behavioral signal pattern."
                ),
                "healthy_streak": 0,
                "signals": current_signals,
            }
        except Exception:
            logger.warning("Local ML model prediction failed -- degrading further.")

    neighbor_result = _nearest_neighbor_fallback(current_signals, memory_dir)
    if neighbor_result is not None:
        return neighbor_result

    return {
        "score": 4,
        "classification": "Watch",
        "rationale": (
            "[Local Fallback Default] Evaluation could not be completed via APIs. "
            "Defaulted to Watch classification as no historical data was available "
            "to train a local model or find a similar match."
        ),
        "healthy_streak": 0,
        "signals": current_signals,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def score_risk(
    employee_name: str,
    signals: list[dict],
    week_number: int,
    memory_dir: str | None = None,
    scorer: RiskScorer | None = None,
    timeline: list[dict] | None = None,
) -> dict:
    """Calculates risk score and classification, loading history and saving current to data\\memory\\.

    Steps:
    1. Load recent memory files (<= MAX_HISTORY_WEEKS old).              [Fix 2]
    2. Compute recurrence bonus with healthy-streak decay.               [Fix 3]
    3. Ask the LLM to score the current signals.
    4. Apply the recurrence bonus on top of the LLM score (capped at 10).
    5. Save result (including healthy_streak) to data\\memory\\firstname_weekN.json.
    """
    # Rule 1: First name only -- never use full name, surname, or ID.
    first_name = first_name_of(employee_name)
    first_name_lower = first_name.lower()

    # Step 1 ---------------------------------------------------------------
    local_dir = memory_dir or MEMORY_DIR
    # [Fix 5] Cap history to weeks strictly before the one being scored, so a
    # chronological re-simulation never reads a "future" week's leftover file.
    history = _load_employee_history(
        first_name_lower, local_dir, before_week=week_number
    )

    # Step 2 ---------------------------------------------------------------
    should_apply_recurrence, current_healthy_streak = _compute_recurrence_bonus(history)

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
        if should_apply_recurrence:
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

    active_scorer = scorer or DEFAULT_SCORER

    try:
        if active_scorer is not None:
            # Deterministic path. Steps 4 and 5 below still run unchanged, so the
            # recurrence and decay rules have exactly one implementation whether
            # the number came from a model or from domain.risk.
            assessment = active_scorer.score(
                first_name,
                _to_signal_models(signals),
                week_number,
                _to_history_models(history),
                _to_week_models(timeline) if timeline else None,
            )
            result = {
                "score": assessment.score,
                "classification": assessment.classification,
                "rationale": assessment.rationale,
                # Phase 2: uncertainty and attribution travel WITH the score.
                # Separating them is how a caveated finding becomes an
                # uncaveated number one layer later (6.1).
                "confidence": assessment.confidence.value,
                "score_range": list(assessment.score_range or ()),
                "attributions": [a.model_dump() for a in assessment.attributions],
            }
            if assessment.insufficient_data:
                result["insufficient_data"] = True
            provenance = "deterministic-scorer"
        else:
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
            provenance = "llm"

        # Phase 3 (6.2): every prediction records which model produced it and
        # on which tier. Without this, a calibration figure cannot be attributed
        # to a version, a regression cannot be traced to the change that caused
        # it, and a rollback has nothing to roll back to.
        result["model_version"] = _active_model_version()
        result["provenance"] = provenance

        # Step 4: Apply recurrence bonus (+1), capped at 10.            [Fix 3]
        if should_apply_recurrence:
            original_score = int(result.get("score", 1))
            adjusted_score = apply_recurrence_bonus(original_score, apply=True)
            result["score"] = adjusted_score
            result["classification"] = _classify(adjusted_score)
            result["rationale"] = (
                str(result.get("rationale", ""))
                + f" [Recurrence adjustment applied: score increased from "
                f"{original_score} to {adjusted_score}.]"
            )

        # Step 5: Determine the new healthy streak for this week.       [Fix 3]
        new_healthy_streak = next_healthy_streak(
            str(result.get("classification", "")), current_healthy_streak
        )
        result["healthy_streak"] = new_healthy_streak  # stored in memory JSON

        # Save to memory ----------------------------------------------------
        os.makedirs(local_dir, exist_ok=True)  # Rule 3: ensure dir exists
        memory_file_name = f"{first_name_lower}_week{week_number}.json"
        current_file_path = os.path.join(local_dir, memory_file_name)

        # Strip internal bookkeeping key before saving.          [Rule 6]
        save_result = {k: v for k, v in result.items() if not k.startswith("_")}
        save_result["signals"] = signals
        with open(current_file_path, "w", encoding="utf-8") as fh:
            json.dump(save_result, fh, indent=2)

        return save_result

    except Exception:
        # Rule 5: Never expose raw Gemini API errors -- attempt Local ML prediction
        fallback = _predict_local_ml_fallback(signals, local_dir)

        # 6.2, "escalating fallback with honesty": a degraded result must SAY it
        # is degraded. A local-ML guess and a Gemini assessment look identical
        # once they are both a number in a JSON file, and a manager reading the
        # second one has no way to know they were handed the first.
        fallback.setdefault("provenance", "local-fallback")
        fallback.setdefault("model_version", _active_model_version())
        fallback.setdefault("confidence", "low")
        fallback["degraded"] = True

        # Still attempt to save the fallback so history remains continuous.
        try:
            os.makedirs(local_dir, exist_ok=True)
            memory_file_name = f"{first_name_lower}_week{week_number}.json"
            fallback_path = os.path.join(local_dir, memory_file_name)
            with open(fallback_path, "w", encoding="utf-8") as fh:
                json.dump(fallback, fh, indent=2)
        except Exception:
            pass  # Rule 5: suppress secondary errors silently

        return fallback
