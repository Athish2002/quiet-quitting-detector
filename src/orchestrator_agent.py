# Quiet Quitting Detector - Orchestrator Agent
# Role: Reads weekly metrics, groups by employee, coordinates execution of other agents, and outputs a master summary.

import csv
import glob
import json
import os

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models import Gemini
from google.adk.runners import InMemoryRunner
from google.genai import types

from src.manager_briefing_agent import generate_briefing
from src.risk_scorer_agent import score_risk

# Import agent pipeline functions
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

    csv_files = glob.glob(os.path.join(weekly_folder, "*.csv"))
    if not csv_files:
        error_msg = "No CSV files found in data/weekly/. Pipeline execution aborted."
        print(error_msg)
        return error_msg

    employee_records = {}
    max_week = 0

    # Sort files chronologically (e.g. week_1.csv, week_2.csv)
    csv_files.sort()

    # Process files
    for file_path in csv_files:
        if not os.path.exists(file_path):  # Rule 3 check
            continue

        filename = os.path.basename(file_path)

        # Parse week number
        week_num = 1
        try:
            name_part = os.path.splitext(filename)[0]
            week_num = int("".join(filter(str.isdigit, name_part)))
        except ValueError:
            pass

        max_week = max(max_week, week_num)

        try:
            with open(file_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Rule 1: First name only
                    raw_name = (
                        row.get("employee_name")
                        or row.get("name")
                        or row.get("first_name")
                        or "Unknown"
                    )
                    first_name = raw_name.split()[0]

                    # Safely convert metrics
                    try:
                        completed_tasks = int(
                            row.get("tasks_completed")
                            or row.get("completed_tasks")
                            or 0
                        )
                    except ValueError:
                        completed_tasks = 0

                    try:
                        response_time = float(
                            row.get("avg_response_time_hours")
                            or row.get("response_time")
                            or 0.0
                        )
                    except ValueError:
                        response_time = 0.0

                    try:
                        after_hours_logins = int(row.get("after_hours_logins") or 0)
                    except ValueError:
                        after_hours_logins = 0

                    try:
                        sick_days = int(row.get("sick_days") or 0)
                    except ValueError:
                        sick_days = 0

                    metrics = {
                        "week": week_num,
                        "completed_tasks": completed_tasks,
                        "response_time": response_time,
                        "after_hours_logins": after_hours_logins,
                        "sick_days": sick_days,
                    }

                    if first_name not in employee_records:
                        employee_records[first_name] = []
                    employee_records[first_name].append(metrics)
        except Exception as e:
            print(f"Error reading CSV file {file_path}: {e}")

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

    runner = InMemoryRunner(agent=orchestrator_agent)

    try:
        events = list(
            runner.run(
                user_id="admin",
                session_id="session_orchestrator_summary",
                new_message=types.Content(
                    role="user", parts=[types.Part.from_text(text=prompt)]
                ),
            )
        )

        report_text = ""
        for event in events:
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        report_text += part.text

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
