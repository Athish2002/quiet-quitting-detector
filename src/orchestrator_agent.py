import json
import os

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models import Gemini

from src.app_utils.runner_helper import run_agent_sync
from src.data_layer.ingestion import ingest_weekly_csvs
from src.data_layer.preprocessing import preprocess_employee_records
from src.manager_briefing_agent import generate_briefing
from src.risk_scorer_agent import score_risk
from src.trend_detector_agent import detect_trends

load_dotenv(override=True)

SYSTEM_INSTRUCTION = """
You are the Quiet-Quitting Orchestrator Agent.
Your job is to compile individual employee reports, summarize disengagement risks, and synthesize a final master briefing report.

Strict Rules:
1. Never use employee surnames or IDs in any output. Only first names are allowed.
2. Never recommend disciplinary action. Focus on supportive responses.
3. If a week of data is missing, note the gap explicitly — do not assume disengagement.
4. Never expose raw Gemini API errors in the final output.
5. All outputs must maintain a warm, supportive, and objective tone.
"""

orchestrator_agent = Agent(
    name="orchestrator_agent",
    model=Gemini(model="gemini-2.5-flash"),
    instruction=SYSTEM_INSTRUCTION,
)


def run_orchestrator() -> str:
    """Orchestrates the entire quiet quitting detection pipeline."""
    weekly_folder = "data/weekly"

    # Rule 3: Always validate that CSV files exist before reading them
    if not os.path.exists(weekly_folder):
        error_msg = f"Data folder '{weekly_folder}' does not exist. Please create it and add weekly CSV files."
        print(error_msg)
        return error_msg

    # Flexible modular ingestion layer
    raw_rows = ingest_weekly_csvs(weekly_folder)
    if not raw_rows:
        error_msg = "No CSV files found in data/weekly/. Pipeline execution aborted."
        print(error_msg)
        return error_msg

    # Modular preprocessing layer
    employee_records, max_week = preprocess_employee_records(raw_rows)
    if not employee_records:
        error_msg = "No valid employee data found in CSV files."
        print(error_msg)
        return error_msg

    pipeline_results = {}

    # Process each employee sequence
    for first_name, weeks_data in employee_records.items():
        weeks_data.sort(key=lambda x: x["week"])

        # Rule 4: If a week of data is missing, note the gap — do not assume disengagement
        processed_weeks = {w["week"] for w in weeks_data}
        expected_weeks = set(range(1, max_week + 1))
        missing_weeks = expected_weeks - processed_weeks

        full_timeline = []
        for w in range(1, max_week + 1):
            if w in processed_weeks:
                week_rec = next(rec for rec in weeks_data if rec["week"] == w)
                full_timeline.append(week_rec)
            else:
                # Add gap indicator
                full_timeline.append(
                    {
                        "week": w,
                        "completed_tasks": None,
                        "response_time": None,
                        "after_hours_logins": None,
                        "sick_days": None,
                        "data_missing": True,
                    }
                )

        # 1. Trend Detector Agent
        signals = detect_trends(first_name, full_timeline)

        # Inject missing data warning explicitly if present
        if missing_weeks:
            signals.append(
                {
                    "signal": "MISSING_DATA_GAP",
                    "severity": "low",
                    "details": f"Missing data for week(s): {sorted(missing_weeks)}. Handled as data gap, not disengagement.",
                }
            )

        # 2. Risk Scorer Agent (save as of max_week)
        risk_data = score_risk(first_name, signals, max_week)

        # 3. Manager Briefing Agent (Only runs for Watch, At Risk, Silent Exit)
        briefing = generate_briefing(first_name, signals, risk_data)

        pipeline_results[first_name] = {
            "signals": signals,
            "risk_data": risk_data,
            "briefing": briefing
            if briefing
            else "No briefing required (Healthy status).",
        }

    # Generate final synthesized report
    prompt = (
        "Synthesize a final report summarizing the quiet-quitting detection process. "
    )
    prompt += "Provide an executive summary of the cohort, followed by details for flagged employees and their briefings.\n"
    prompt += json.dumps(pipeline_results, indent=2)

    try:
        report_text = run_agent_sync(
            orchestrator_agent,
            user_id="admin",
            session_id="session_orchestrator_summary",
            prompt=prompt,
        )

        print("\n=== SYSTEM EXECUTION COMPLETED ===")
        return report_text.strip()
    except Exception:
        # Respect Rule 5: Never expose raw Gemini API errors
        fallback_msg = (
            "Quiet-Quitting Detection Report\n"
            "------------------------------\n"
            "An error occurred while compiling the final executive report. "
            "However, individual agent analyses have run successfully. "
            "Please check the data/memory/ directory for stored risk scoring files."
        )
        return fallback_msg


if __name__ == "__main__":
    report = run_orchestrator()
    print(report)
