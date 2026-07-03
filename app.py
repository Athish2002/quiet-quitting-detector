import csv
import glob
import json
import os
import random

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from google.adk.agents import Agent
from google.adk.models import Gemini
from pydantic import BaseModel

from src.app_utils.runner_helper import run_agent_sync
from src.orchestrator_agent import run_orchestrator

# Initialize the natural language metric extraction agent
extractor_agent = Agent(
    name="extractor_agent",
    model=Gemini(model="gemini-3.1-flash-lite"),
    instruction="""
    You are an expert data extraction assistant.
    Your task is to parse a text description of employee metrics and output a JSON block matching this schema:
    {
      "employee_name": "Name",
      "tasks_completed": 10,
      "avg_response_time_hours": 1.5,
      "after_hours_logins": 2,
      "sick_days": 1
    }
    Only output valid JSON. Do not write explanations or conversational text.
    """,
)

app = FastAPI(
    title="Quiet-Quitting Detector UI",
    description="Interactive Multi-Agent Dashboard for Employee Engagement Tracking",
    version="1.0.0",
)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MEMORY_DIR = "data/memory"
WEEKLY_DIR = "data/weekly"


@app.post("/api/run")
def execute_pipeline():
    """Triggers the full multi-agent pipeline and returns the summary."""
    try:
        report_output = run_orchestrator()
        return {
            "success": True,
            "message": "Pipeline completed successfully.",
            "report_preview": report_output[:2000] + "...",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Pipeline execution failed: {e!s}"
        ) from e


@app.get("/api/employees")
def get_employees_status():
    """Loads all employees' final classifications and metrics based on memory files."""
    if not os.path.exists(MEMORY_DIR):
        return []

    memory_files = glob.glob(os.path.join(MEMORY_DIR, "*.json"))
    records = {}

    for path in memory_files:
        filename = os.path.basename(path)
        # Parse name and week from filename (e.g. arjun_week4.json)
        parts = filename.replace(".json", "").split("_week")
        if len(parts) != 2:
            continue

        name = parts[0].capitalize()
        try:
            week = int(parts[1])
        except ValueError:
            continue

        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue

        if name not in records:
            records[name] = {}

        records[name][week] = data

    # Compile the final status of each employee
    summary = []
    for name, weeks_data in records.items():
        if not weeks_data:
            continue
        # Get the latest week
        latest_week = max(weeks_data.keys())
        latest_status = weeks_data[latest_week]

        summary.append(
            {
                "name": name,
                "score": latest_status.get("score", 1),
                "classification": latest_status.get("classification", "Healthy"),
                "rationale": latest_status.get("rationale", ""),
                "latest_week": latest_week,
                "history": [
                    {
                        "week": w,
                        "score": weeks_data[w].get("score", 1),
                        "classification": weeks_data[w].get(
                            "classification", "Healthy"
                        ),
                    }
                    for w in sorted(weeks_data.keys())
                ],
            }
        )

    # Sort alphabetical
    summary.sort(key=lambda x: x["name"])
    return summary


@app.get("/api/employee/{name}/briefing")
def get_employee_briefing(name: str):
    """Loads the manager briefing card contents from the final report file for the specified employee."""
    report_path = "engagement_report.txt"
    if not os.path.exists(report_path):
        raise HTTPException(
            status_code=404, detail="Engagement report not generated yet."
        )

    name.strip().lower()
    try:
        with open(report_path, encoding="utf-8") as fh:
            content = fh.read()
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Could not read report file: {e!s}"
        ) from e

    # Find the employee card block in the report
    marker = f"Employee      : {name.capitalize()}"
    if marker not in content:
        # Check if the name exists inside the raw file
        return {
            "found": False,
            "briefing": "No individual briefing card found for this employee.",
        }

    # Extract block between this card and the next line separator
    try:
        start_idx = content.find(marker)
        # End of the block is either the next "-----" or the end of the report
        next_sep = content.find(
            "------------------------------------------------------------------------",
            start_idx + len(marker),
        )
        if next_sep == -1:
            block = content[start_idx:]
        else:
            block = content[start_idx:next_sep]

        return {"found": True, "raw_card": block.strip()}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to parse briefing block: {e!s}"
        ) from e


@app.get("/api/report/raw")
def get_raw_report():
    """Serves the raw generated engagement_report.txt file."""
    report_path = "engagement_report.txt"
    if os.path.exists(report_path):
        return FileResponse(report_path, media_type="text/plain")
    raise HTTPException(status_code=404, detail="Engagement report file not found.")


@app.post("/api/memory/clear")
def clear_pipeline_data():
    """Deletes all employee memory JSON files and the master engagement report."""
    try:
        # Clear memory files
        if os.path.exists(MEMORY_DIR):
            files = glob.glob(os.path.join(MEMORY_DIR, "*.json"))
            for f in files:
                os.remove(f)

        # Clear raw report
        report_path = "engagement_report.txt"
        if os.path.exists(report_path):
            os.remove(report_path)

        return {"success": True, "message": "All pipeline data and memory cleared."}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to clear memory: {e!s}"
        ) from e


@app.post("/api/mock-data")
def generate_mock_data():
    """Generates 4 weekly CSV files with randomized employee trajectories."""
    try:
        os.makedirs(WEEKLY_DIR, exist_ok=True)
        employees = ["Arjun", "Priya", "Karthik", "Divya", "Ravi", "Meena"]

        # Define baseline trajectories for variance
        trajectories = {
            "Arjun": {
                1: {"tasks": 9, "response": 0.8, "after_hours": 0, "sick": 0},
                2: {"tasks": 7, "response": 1.4, "after_hours": 1, "sick": 0},
                3: {"tasks": 5, "response": 3.0, "after_hours": 2, "sick": 1},
                4: {"tasks": 3, "response": 5.0, "after_hours": 3, "sick": 2},
            },
            "Priya": {
                1: {"tasks": 8, "response": 1.0, "after_hours": 0, "sick": 0},
                2: {"tasks": 7, "response": 1.8, "after_hours": 1, "sick": 0},
                3: {"tasks": 5, "response": 2.8, "after_hours": 1, "sick": 1},
                4: {"tasks": 4, "response": 3.6, "after_hours": 2, "sick": 1},
            },
            "Karthik": {
                1: {"tasks": 9, "response": 0.9, "after_hours": 0, "sick": 0},
                2: {"tasks": 7, "response": 1.5, "after_hours": 1, "sick": 0},
                3: {"tasks": 6, "response": 2.5, "after_hours": 2, "sick": 1},
                4: {"tasks": 8, "response": 1.2, "after_hours": 1, "sick": 0},
            },
            "Divya": {
                1: {"tasks": 10, "response": 0.5, "after_hours": 0, "sick": 0},
                2: {"tasks": 9, "response": 0.6, "after_hours": 0, "sick": 0},
                3: {"tasks": 10, "response": 0.5, "after_hours": 0, "sick": 0},
                4: {"tasks": 9, "response": 0.6, "after_hours": 0, "sick": 0},
            },
            "Ravi": {
                1: {"tasks": 9, "response": 0.6, "after_hours": 0, "sick": 0},
                2: {"tasks": 8, "response": 0.7, "after_hours": 1, "sick": 0},
                3: {"tasks": 9, "response": 0.6, "after_hours": 0, "sick": 0},
                4: {"tasks": 9, "response": 0.7, "after_hours": 0, "sick": 0},
            },
            "Meena": {
                1: {"tasks": 8, "response": 0.8, "after_hours": 0, "sick": 0},
                2: {"tasks": 6, "response": 1.5, "after_hours": 1, "sick": 0},
                3: {"tasks": 5, "response": 2.2, "after_hours": 2, "sick": 1},
                4: {"tasks": 5, "response": 2.0, "after_hours": 1, "sick": 1},
            },
        }

        # Write 4 CSV files
        for w in range(1, 5):
            csv_path = os.path.join(WEEKLY_DIR, f"week{w}.csv")
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "employee_name",
                        "tasks_completed",
                        "avg_response_time_hours",
                        "after_hours_logins",
                        "sick_days",
                    ]
                )
                for emp in employees:
                    base = trajectories[emp][w]
                    # Add small random fluctuation
                    tasks = max(0, base["tasks"] + random.choice([-1, 0, 1]))
                    resp = round(
                        max(0.1, base["response"] + random.uniform(-0.2, 0.2)), 2
                    )
                    after = (
                        max(0, base["after_hours"] + random.choice([0, 1]))
                        if base["after_hours"] > 0
                        else 0
                    )
                    sick = (
                        max(0, base["sick"] + random.choice([0, 1]))
                        if base["sick"] > 0
                        else 0
                    )
                    writer.writerow([emp, tasks, resp, after, sick])

        return {"success": True, "message": "Mock data synthesized successfully."}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate mock data: {e!s}"
        ) from e


class RawCSVInput(BaseModel):
    week_number: int
    csv_content: str


@app.post("/api/ingest/raw")
def ingest_raw_csv(data: RawCSVInput):
    """Directly ingests pasted raw CSV content in the browser for a given week number."""
    try:
        os.makedirs(WEEKLY_DIR, exist_ok=True)
        file_path = os.path.join(WEEKLY_DIR, f"week{data.week_number}.csv")
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write(data.csv_content.strip())
        return {
            "success": True,
            "message": f"Raw CSV for week {data.week_number} saved.",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to save raw CSV: {e!s}"
        ) from e


class CustomEvaluatorInput(BaseModel):
    name: str
    week_number: int
    tasks_completed: int
    avg_response_time: float
    after_hours_logins: int
    sick_days: int
    previous_classification: str = "Healthy"
    consecutive_weeks_elevated: int = 0
    weekly_hours: int = 40
    task_accuracy: int = 95
    sentiment: str = "Neutral"


@app.post("/api/score/custom")
def score_custom_employee(data: CustomEvaluatorInput):
    """Evaluates a single custom employee metrics record in memory, running risk scorer and briefing agents."""
    try:
        from src.manager_briefing_agent import generate_briefing
        from src.risk_scorer_agent import score_risk
        from src.trend_detector_agent import detect_trends

        name = data.name.strip().split()[0].capitalize()
        name_lower = name.lower()

        # 1. Synthesize mock history file for memory load if provided
        if data.previous_classification != "Healthy":
            os.makedirs(MEMORY_DIR, exist_ok=True)
            # Write a mock history file for the preceding week
            prev_week = data.week_number - 1
            if prev_week > 0:
                mock_hist = {
                    "score": (
                        6
                        if data.previous_classification == "At Risk"
                        else (8 if data.previous_classification == "Silent Exit" else 4)
                    ),
                    "classification": data.previous_classification,
                    "rationale": "Mocked historical classification.",
                    "healthy_streak": 0,
                }
                hist_path = os.path.join(
                    MEMORY_DIR, f"{name_lower}_week{prev_week}.json"
                )
                with open(hist_path, "w", encoding="utf-8") as fh:
                    json.dump(mock_hist, fh, indent=2)

        # 2. Build full timeline of week 1 (baseline) and current week
        baseline = {
            "week": 1,
            "completed_tasks": 10,
            "response_time": 0.5,
            "after_hours_logins": 0,
            "sick_days": 0,
        }
        current = {
            "week": data.week_number,
            "completed_tasks": data.tasks_completed,
            "response_time": data.avg_response_time,
            "after_hours_logins": data.after_hours_logins,
            "sick_days": data.sick_days,
        }

        # Run Trend Detector
        signals = detect_trends(name, [baseline, current])

        # Run Risk Scorer
        risk_data = score_risk(name, signals, data.week_number)

        # Run Briefing
        briefing = generate_briefing(name, signals, risk_data)

        return {
            "success": True,
            "employee_name": name,
            "signals": signals,
            "risk_data": risk_data,
            "briefing": briefing
            if briefing
            else "No briefing required (Healthy status).",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Custom evaluation failed: {e!s}"
        ) from e


class DatabaseSyncInput(BaseModel):
    db_url: str
    table_name: str
    target_week: int


class S3SyncInput(BaseModel):
    s3_uri: str
    target_week: int


@app.post("/api/ingest/db")
def ingest_from_db(data: DatabaseSyncInput):
    """Simulates ingesting data from a central corporate SQL database."""
    try:
        os.makedirs(WEEKLY_DIR, exist_ok=True)
        file_path = os.path.join(WEEKLY_DIR, f"week{data.target_week}.csv")
        file_exists = os.path.exists(file_path)
        with open(file_path, "a", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            if not file_exists:
                writer.writerow(
                    [
                        "employee_name",
                        "tasks_completed",
                        "avg_response_time_hours",
                        "after_hours_logins",
                        "sick_days",
                    ]
                )
            writer.writerow(["Karthik", "7", "1.1", "0", "0"])
            writer.writerow(["Divya", "10", "0.4", "0", "0"])
        return {
            "success": True,
            "message": f"Successfully synchronized 2 employee records from Database table '{data.table_name}' for Week {data.target_week}.",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Database synchronization failed: {e!s}"
        ) from e


@app.post("/api/ingest/s3")
def ingest_from_s3(data: S3SyncInput):
    """Simulates ingesting data from AWS S3 cloud buckets."""
    try:
        os.makedirs(WEEKLY_DIR, exist_ok=True)
        file_path = os.path.join(WEEKLY_DIR, f"week{data.target_week}.csv")
        file_exists = os.path.exists(file_path)
        with open(file_path, "a", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            if not file_exists:
                writer.writerow(
                    [
                        "employee_name",
                        "tasks_completed",
                        "avg_response_time_hours",
                        "after_hours_logins",
                        "sick_days",
                    ]
                )
            writer.writerow(["Ravi", "9", "0.6", "0", "0"])
        return {
            "success": True,
            "message": f"Successfully downloaded bucket content from S3 path '{data.s3_uri}' for Week {data.target_week}.",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Cloud download failed: {e!s}"
        ) from e


class NaturalLanguageInput(BaseModel):
    week_number: int
    text_prompt: str


@app.post("/api/ingest/natural-language")
def ingest_natural_language(data: NaturalLanguageInput):
    """Parses a natural language prompt to extract metrics using LLM and saves it as a CSV record."""
    try:
        raw_json_str = run_agent_sync(
            extractor_agent,
            user_id="admin",
            session_id=f"session_extract_{random.randint(1000, 9999)}",
            prompt=data.text_prompt,
        )

        clean_str = raw_json_str.strip()
        if clean_str.startswith("```"):
            lines = clean_str.split("\n")
            clean_str = "\n".join(
                [line for line in lines if not line.startswith("```")]
            )

        extracted = json.loads(clean_str.strip())

        name = extracted.get("employee_name", "Unknown").strip().capitalize()
        tasks = int(extracted.get("tasks_completed", 0))
        resp = float(extracted.get("avg_response_time_hours", 0.0))
        after = int(extracted.get("after_hours_logins", 0))
        sick = int(extracted.get("sick_days", 0))

        os.makedirs(WEEKLY_DIR, exist_ok=True)
        file_path = os.path.join(WEEKLY_DIR, f"week{data.week_number}.csv")

        file_exists = os.path.exists(file_path)
        with open(file_path, "a", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            if not file_exists:
                writer.writerow(
                    [
                        "employee_name",
                        "tasks_completed",
                        "avg_response_time_hours",
                        "after_hours_logins",
                        "sick_days",
                    ]
                )
            writer.writerow([name, tasks, resp, after, sick])

        return {
            "success": True,
            "extracted": {
                "name": name,
                "tasks_completed": tasks,
                "avg_response_time": resp,
                "after_hours_logins": after,
                "sick_days": sick,
            },
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to extract metrics: {e!s}"
        ) from e


# Serve static web files
if os.path.exists("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
else:

    @app.get("/", response_class=HTMLResponse)
    def index_fallback():
        return """
        <html>
            <body style="font-family: sans-serif; text-align: center; padding-top: 100px;">
                <h1>Quiet-Quitting Detector Server Running</h1>
                <p>Please create the static/ directory and place index.html inside it to load the dashboard.</p>
            </body>
        </html>
        """


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
