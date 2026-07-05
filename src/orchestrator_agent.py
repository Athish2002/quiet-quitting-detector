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


def run_orchestrator(
    weekly_folder: str = "data/weekly", memory_folder: str = "data/memory"
) -> str:
    """Orchestrates the entire quiet quitting detection pipeline."""

    # Rule 3: Always validate that CSV files exist before reading them
    if not os.path.exists(weekly_folder):
        error_msg = f"Data folder '{weekly_folder}' does not exist. Please create it and add weekly CSV files."
        print(error_msg)
        return error_msg

    # Flexible modular ingestion layer
    raw_rows = ingest_weekly_csvs(weekly_folder)
    if not raw_rows:
        error_msg = (
            f"No CSV files found in {weekly_folder}. Pipeline execution aborted."
        )
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
        expected_weeks - processed_weeks

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

        # We will sequentially evaluate each week from 1 to max_week to build chronological history
        last_risk_data = None
        last_briefing = None
        last_signals = None

        for w in range(1, max_week + 1):
            memory_file_name = f"{first_name.lower()}_week{w}.json"
            memory_file_path = os.path.join(memory_folder, memory_file_name)

            # Check if this week's evaluation already exists in memory
            if os.path.exists(memory_file_path):
                try:
                    with open(memory_file_path, encoding="utf-8") as f:
                        risk_data = json.load(f)
                    briefing = risk_data.get("briefing", "")
                    signals = risk_data.get("signals", [])

                    # If it's not Healthy but briefing is missing, we can generate it
                    if not briefing and risk_data.get(
                        "classification", ""
                    ).upper() not in ["HEALTHY"]:
                        sub_timeline = full_timeline[:w]
                        w_missing = expected_weeks.intersection(
                            range(1, w + 1)
                        ) - processed_weeks.intersection(range(1, w + 1))
                        signals = detect_trends(first_name, sub_timeline)
                        if w_missing:
                            signals.append(
                                {
                                    "signal": "MISSING_DATA_GAP",
                                    "severity": "low",
                                    "details": f"Missing data for week(s): {sorted(w_missing)}. Handled as data gap, not disengagement.",
                                }
                            )
                        briefing = generate_briefing(
                            first_name, signals, risk_data, memory_dir=memory_folder
                        )
                        if briefing:
                            risk_data["briefing"] = briefing
                            risk_data["signals"] = signals
                            with open(memory_file_path, "w", encoding="utf-8") as f:
                                json.dump(risk_data, f, indent=2)
                except Exception:
                    sub_timeline = full_timeline[:w]
                    w_missing = expected_weeks.intersection(
                        range(1, w + 1)
                    ) - processed_weeks.intersection(range(1, w + 1))
                    signals = detect_trends(first_name, sub_timeline)
                    if w_missing:
                        signals.append(
                            {
                                "signal": "MISSING_DATA_GAP",
                                "severity": "low",
                                "details": f"Missing data for week(s): {sorted(w_missing)}. Handled as data gap, not disengagement.",
                            }
                        )
                    risk_data = score_risk(
                        first_name, signals, w, memory_dir=memory_folder
                    )
                    briefing = generate_briefing(
                        first_name, signals, risk_data, memory_dir=memory_folder
                    )
                    risk_data["signals"] = signals
                    if briefing:
                        risk_data["briefing"] = briefing
                    with open(memory_file_path, "w", encoding="utf-8") as f:
                        json.dump(risk_data, f, indent=2)
            else:
                # If memory file doesn't exist, execute agents chronologically
                sub_timeline = full_timeline[:w]
                w_missing = expected_weeks.intersection(
                    range(1, w + 1)
                ) - processed_weeks.intersection(range(1, w + 1))

                # 1. Trend Detector Agent
                signals = detect_trends(first_name, sub_timeline)
                if w_missing:
                    signals.append(
                        {
                            "signal": "MISSING_DATA_GAP",
                            "severity": "low",
                            "details": f"Missing data for week(s): {sorted(w_missing)}. Handled as data gap, not disengagement.",
                        }
                    )

                # 2. Risk Scorer Agent (save as of week w)
                risk_data = score_risk(first_name, signals, w, memory_dir=memory_folder)

                # 3. Manager Briefing Agent (Only runs for Watch, At Risk, Silent Exit)
                briefing = generate_briefing(
                    first_name, signals, risk_data, memory_dir=memory_folder
                )

                risk_data["signals"] = signals
                if briefing:
                    risk_data["briefing"] = briefing
                with open(memory_file_path, "w", encoding="utf-8") as f:
                    json.dump(risk_data, f, indent=2)

            if w == max_week:
                last_risk_data = risk_data
                last_briefing = briefing
                last_signals = signals

        pipeline_results[first_name] = {
            "signals": last_signals,
            "risk_data": last_risk_data,
            "briefing": last_briefing
            if last_briefing
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
