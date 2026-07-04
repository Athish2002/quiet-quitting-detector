import csv
import glob
import json
import os
import random

from fastapi import FastAPI, HTTPException, Response
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
      "sick_days": 1,
      "weekly_hours": 40,
      "task_accuracy": 95,
      "sentiment": "Neutral"
    }
    Only output valid JSON. Do not write explanations or conversational text.
    """,
)

app = FastAPI(
    title="Quiet-Quitting Detector UI",
    description="Interactive Multi-Agent Dashboard for Employee Engagement Tracking",
    version="1.0.0",
)

# Enable CORS for development/production
allow_origins = os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else ["http://localhost:8000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MEMORY_DIR = "data/memory"
WEEKLY_DIR = "data/weekly"


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


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
    """Loads the manager briefing card contents from the employee's latest memory file."""
    name_lower = name.strip().lower()
    pattern = os.path.join(MEMORY_DIR, f"{name_lower}_week*.json")
    memory_files = glob.glob(pattern)
    
    if not memory_files:
        return {
            "found": False,
            "briefing": "No individual briefing card found for this employee.",
        }
        
    # Get the latest week file
    latest_file = max(memory_files, key=lambda x: int(os.path.basename(x).replace(f"{name_lower}_week", "").replace(".json", "")))
    
    try:
        with open(latest_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        if "briefing" in data and data["briefing"]:
            return {
                "found": True,
                "briefing": data["briefing"],
                "raw_card": data["briefing"]
            }
        else:
            return {
                "found": False,
                "briefing": "No individual briefing card found for this employee.",
                "raw_card": ""
            }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Could not read memory file: {e!s}"
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
        os.makedirs(MEMORY_DIR, exist_ok=True)
        
        # Clear existing CSV and Memory files for a fresh start
        for f in glob.glob(os.path.join(WEEKLY_DIR, "*.csv")):
            os.remove(f)
        for f in glob.glob(os.path.join(MEMORY_DIR, "*.json")):
            os.remove(f)

        employees = ["Arjun", "Priya", "Karthik", "Divya", "Ravi", "Meena"]

        # Assign roles probabilistically for true randomization
        emp_profiles = {}
        for emp in employees:
            r = random.random()
            if r < 0.15:
                emp_profiles[emp] = "Silent Exit"
            elif r < 0.30:
                emp_profiles[emp] = "At Risk"
            elif r < 0.45:
                emp_profiles[emp] = "Watch"
            else:
                emp_profiles[emp] = "Healthy"

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
                        "weekly_hours",
                        "task_accuracy",
                        "sentiment"
                    ]
                )
                for emp in employees:
                    profile = emp_profiles[emp]
                    if profile == "Silent Exit":
                        # Gradual disengagement collapse with random variance
                        tasks = max(1, 10 - int(w * 2.5) + random.randint(-1, 1))
                        resp = round(max(0.5, 0.4 + w * 1.2 + random.uniform(-0.4, 0.6)), 2)
                        after = random.randint(1, max(1, w))
                        sick = random.randint(0, max(0, w - 2))
                        hours = max(35, 45 - (w * 2) + random.randint(-2, 2))
                        acc = max(70, 98 - (w * 5) + random.randint(-5, 5))
                        sent = random.choice(["Negative", "Neutral"]) if w > 2 else "Neutral"
                    elif profile == "At Risk":
                        # Moderate disengagement trend
                        tasks = max(2, 10 - int(w * 1.5) + random.randint(-2, 1))
                        resp = round(max(0.4, 0.5 + w * 0.6 + random.uniform(-0.2, 0.4)), 2)
                        after = random.randint(0, max(1, w - 1))
                        sick = random.randint(0, 1)
                        hours = max(38, 48 - (w * 1.5) + random.randint(-3, 3))
                        acc = max(75, 95 - (w * 3) + random.randint(-3, 3))
                        sent = random.choice(["Neutral", "Negative"])
                    elif profile == "Watch":
                        # Short decline with week 4 recovery
                        if w == 3:
                            tasks = random.randint(4, 6)
                            resp = round(random.uniform(1.5, 2.5), 2)
                            after = random.randint(1, 2)
                            sick = random.randint(0, 1)
                            hours = random.randint(50, 60)
                            acc = random.randint(80, 85)
                            sent = "Negative"
                        elif w == 4:
                            tasks = random.randint(8, 10)  # Recovery
                            resp = round(random.uniform(0.5, 1.2), 2)
                            after = 0
                            sick = 0
                            hours = random.randint(40, 42)
                            acc = random.randint(92, 98)
                            sent = "Positive"
                        else:
                            tasks = max(5, 10 - w + random.randint(-1, 0))
                            resp = round(0.5 + w * 0.3 + random.uniform(-0.1, 0.2), 2)
                            after = 0
                            sick = 0
                            hours = random.randint(42, 48)
                            acc = random.randint(88, 95)
                            sent = "Neutral"
                    else:
                        # Healthy stable baseline
                        tasks = random.randint(8, 11)
                        resp = round(max(0.2, 0.4 + random.uniform(-0.15, 0.2)), 2)
                        after = random.choice([0, 0, 1])
                        sick = 0
                        hours = random.randint(38, 42)
                        acc = random.randint(94, 100)
                        sent = random.choice(["Positive", "Neutral"])

                    writer.writerow([emp, int(tasks), resp, after, sick, int(hours), int(acc), sent])

                    # Write mock memory files for weeks 1-3 so history renders in the UI
                    if w < 4:
                        # Base score assignment with random variance
                        if profile == "Silent Exit":
                            base_sc = 3 if w == 1 else (6 if w == 2 else 8)
                        elif profile == "At Risk":
                            base_sc = 2 if w == 1 else (4 if w == 2 else 6)
                        elif profile == "Watch":
                            base_sc = 2 if w == 1 else (3 if w == 2 else 4)
                        else:
                            base_sc = 1
                        
                        # Add variance
                        sc = max(1, min(10, base_sc + random.randint(-1, 1)))
                        
                        # Determine classification and context-aware dynamic rationale
                        if sc <= 2:
                            cls_val = "Healthy"
                            rat_val = f"Operational baseline assessment. Stable tasks volume ({int(tasks)} completed) and standard latency."
                        elif sc <= 4:
                            cls_val = "Watch"
                            rat_val = f"Early indicator check. Elevated response time ({resp}h) or marginal decrease in task accuracy ({int(acc)}%)."
                        elif sc <= 7:
                            cls_val = "At Risk"
                            rat_val = f"Disengagement warning. Persistent declines in task performance and low weekly hours ({int(hours)}h)."
                        else:
                            cls_val = "Silent Exit"
                            rat_val = f"Severe disengagement flags. Consecutive drop in productivity and communication latency spikes."
                        
                        # Simulate pre-detected signals list for memory file parity
                        mock_signals = []
                        if tasks < 7:
                            mock_signals.append({"signal_name": "Declining Task Completion", "weeks_detected": [w], "severity": "medium" if tasks >= 4 else "high"})
                        if resp > 1.5:
                            mock_signals.append({"signal_name": "Response Time Spike", "weeks_detected": [w], "severity": "high" if resp > 2.2 else "medium"})
                        if after > 2:
                            mock_signals.append({"signal_name": "Excessive After-Hours Logins", "weeks_detected": [w], "severity": "medium"})
                        if sick > 1:
                            mock_signals.append({"signal_name": "Increasing Sick Days", "weeks_detected": [w], "severity": "high"})
                        if acc < 85:
                            mock_signals.append({"signal_name": "Quality Degradation", "weeks_detected": [w], "severity": "medium"})

                        mock_memory = {
                            "score": sc,
                            "classification": cls_val,
                            "rationale": rat_val,
                            "healthy_streak": w if sc <= 2 else 0,
                            "signals": mock_signals
                        }
                        mem_path = os.path.join(MEMORY_DIR, f"{emp.lower()}_week{w}.json")
                        with open(mem_path, "w", encoding="utf-8") as mf:
                            json.dump(mock_memory, mf, indent=2)

        return {
            "success": True,
            "message": "Successfully generated new randomized weekly metric logs.",
        }
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
            # Write mock history files for the preceding weeks based on consecutive_weeks_elevated
            weeks_to_mock = max(1, data.consecutive_weeks_elevated)
            for i in range(weeks_to_mock):
                prev_week = data.week_number - 1 - i
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
            "weekly_hours": 40,
            "task_accuracy": 95,
            "sentiment": "Neutral",
        }
        current = {
            "week": data.week_number,
            "completed_tasks": data.tasks_completed,
            "response_time": data.avg_response_time,
            "after_hours_logins": data.after_hours_logins,
            "sick_days": data.sick_days,
            "weekly_hours": data.weekly_hours,
            "task_accuracy": data.task_accuracy,
            "sentiment": data.sentiment,
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
                        "weekly_hours",
                        "task_accuracy",
                        "sentiment"
                    ]
                )
            writer.writerow(["Karthik", "7", "1.1", "0", "0", "42", "94", "Neutral"])
            writer.writerow(["Divya", "10", "0.4", "0", "0", "38", "98", "Positive"])
        return {
            "success": True,
            "message": f"Successfully synchronized 2 employee records (with Weekly Hours, Task Accuracy, Sentiment) from Database table '{data.table_name}' for Week {data.target_week}.",
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
                        "weekly_hours",
                        "task_accuracy",
                        "sentiment"
                    ]
                )
            writer.writerow(["Ravi", "9", "0.6", "0", "0", "40", "96", "Positive"])
        return {
            "success": True,
            "message": f"Successfully downloaded bucket content (with Weekly Hours, Task Accuracy, Sentiment) from S3 path '{data.s3_uri}' for Week {data.target_week}.",
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
        hours = int(extracted.get("weekly_hours", random.randint(35, 45)))
        acc = int(extracted.get("task_accuracy", random.randint(85, 100)))
        sent = str(extracted.get("sentiment", random.choice(["Positive", "Neutral", "Negative"]))).strip().capitalize()

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
                        "weekly_hours",
                        "task_accuracy",
                        "sentiment"
                    ]
                )
            writer.writerow([name, tasks, resp, after, sick, hours, acc, sent])

        return {
            "success": True,
            "extracted": {
                "name": name,
                "tasks_completed": tasks,
                "avg_response_time": resp,
                "after_hours_logins": after,
                "sick_days": sick,
                "weekly_hours": hours,
                "task_accuracy": acc,
                "sentiment": sent,
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
