import csv
import glob
import io
import json
import logging
import os
import random
import threading

from dotenv import find_dotenv, load_dotenv

# Load .env FIRST, before importing anything that reads configuration at import
# time. Under `uvicorn app:app` the agent modules' own load_dotenv() calls run
# too late (or not at all) for env-gated config read during app import, so
# without this the server starts with no API keys in os.environ at all --
# every provider silently drops to the local fallback tiers.
load_dotenv(find_dotenv(usecwd=True), override=False)

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from google.adk.agents import Agent
from google.adk.models import Gemini
from pydantic import BaseModel, Field

from src.app_utils import progress
from src.app_utils.audit_log import clear_events, log_event, read_events
from src.app_utils.local_nl_extract import extract_metrics_from_text
from src.app_utils.names import first_name_of
from src.app_utils.runner_helper import METRICS_FILE, get_model_status, run_agent_sync
from src.app_utils.settings import get_settings, is_local_only_mode, set_local_only_mode
from src.data_layer.ingestion import (
    MAX_WEEK,
    MIN_WEEK,
    group_rows_by_week,
    ingest_weekly_csvs,
    merge_rows_into_weekly_csv,
    normalize_row_to_canonical,
)
from src.data_layer.preprocessing import preprocess_employee_records
from src.data_layer.s3_store import bucket_stats, fetch_object
from src.data_layer.sql_store import db_stats, seed_sample_corporate_batch
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

    Guidelines to widen matching and fuzzy logic mapping:
    - If a metric is not mentioned in the text, estimate a reasonable default value or leave it blank (e.g. 0 for sick days, 40 for weekly hours, 95 for accuracy, "Neutral" for sentiment).
    - Map synonyms and behavioral descriptions flexibly:
      * "holiday", "absences", "leaves", "days off", "vacation" -> map to "sick_days"
      * "worked X hours", "spent X hours", "only for X hours" -> map to "weekly_hours"
      * "worked everyday", "night logins", "late logins", "after-hours" -> map to "after_hours_logins"
      * "accuracy", "quality", "score", "performance accuracy" -> map to "task_accuracy"
      * "latency", "response", "delay", "avg response", "response speed" -> map to "avg_response_time_hours"
    - Only output valid JSON. Do not write explanations or conversational text.
    """,
)

app = FastAPI(
    title="Quiet-Quitting Detector UI",
    description="Interactive Multi-Agent Dashboard for Employee Engagement Tracking",
    version="1.0.0",
)

# Enable CORS for development/production
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",")
    if os.getenv("ALLOW_ORIGINS")
    else ["http://localhost:8000"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


MEMORY_DIR = "data/memory"
WEEKLY_DIR = "data/weekly"
REALTIME_DIR = "data/realtime"
REALTIME_MEMORY_DIR = "data/realtime_memory"
SIMULATOR_MEMORY_DIR = "data/simulator_memory"
MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB -- generous for a weekly metrics CSV


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/api/metrics")
def get_metrics():
    """Returns the API usage metrics (success vs rejected).

    Reads the same path the writer uses (METRICS_FILE) instead of a duplicated
    literal, so overriding API_METRICS_PATH can't desync reader and writer.
    """
    if os.path.exists(METRICS_FILE):
        try:
            with open(METRICS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {
                    "success": int(data.get("success", 0) or 0),
                    "rejected": int(data.get("rejected", 0) or 0),
                }
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            logging.getLogger(__name__).debug(
                "API metrics unreadable; reporting zeros.", exc_info=True
            )
    return {"success": 0, "rejected": 0}


@app.get("/api/settings")
def get_settings_endpoint():
    """Returns persisted app settings (currently just Local-Only Mode)."""
    return get_settings()


class SettingsUpdateInput(BaseModel):
    local_only_mode: bool


@app.post("/api/settings")
def update_settings_endpoint(data: SettingsUpdateInput):
    """Toggles Local-Only Mode -- when enabled, every Gemini call is skipped
    immediately and routed straight to the local fallback tiers, so the user
    can deliberately stop spending quota once they know they're rate-limited."""
    result = set_local_only_mode(data.local_only_mode)
    log_event(
        "settings_change",
        "settings",
        f"Local-Only Mode {'enabled' if data.local_only_mode else 'disabled'}",
    )
    return result


@app.get("/api/models/status")
def get_models_status():
    """Reports the real, current Gemini model-fallback state -- which models
    are actually in a 60s exhaustion cooldown right now, which one last
    succeeded, and whether Local-Only Mode is skipping all of them by
    choice. The UI uses this instead of guessing exhaustion from a
    cumulative counter."""
    status = get_model_status()
    status["local_only_mode"] = is_local_only_mode()
    return status


@app.get("/api/history")
def get_history(limit: int = 200):
    """Returns the audit log of ingestion events and pipeline runs, newest first."""
    return read_events(limit=limit)


@app.post("/api/history/clear")
def clear_history():
    """Clears the audit log (does not affect employee data)."""
    clear_events()
    return {"success": True, "message": "History log cleared."}


def _run_pipeline_in_background(
    scope: str, weekly_folder: str, memory_folder: str, report_path: str
) -> None:
    """Runs the orchestrator on a background thread so the HTTP request can
    return immediately, and the UI can poll /api/run/progress for a real,
    moving progress bar instead of blocking on an indefinite spinner."""

    def _worker() -> None:
        try:
            try:
                raw_rows = ingest_weekly_csvs(weekly_folder)
                employee_records, max_week = preprocess_employee_records(raw_rows)
                total = max(1, len(employee_records) * max(max_week, 1))
            except Exception:
                logging.getLogger(__name__).warning(
                    "Could not pre-compute progress total for the %s run; "
                    "falling back to an indeterminate count.",
                    scope,
                    exc_info=True,
                )
                total = 1
            # The slot was already reserved by the caller via progress.try_start();
            # this only fills in the now-known unit count.
            progress.set_total(total)

            report_output = run_orchestrator(
                weekly_folder=weekly_folder,
                memory_folder=memory_folder,
                progress_cb=lambda label: progress.update(label),
            )
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report_output)
            log_event("pipeline_run", scope, f"{scope.capitalize()} cohort evaluated.")
            progress.finish()
        except Exception as e:
            log_event("pipeline_run", scope, str(e), success=False)
            progress.finish(error=str(e))

    try:
        threading.Thread(target=_worker, daemon=True).start()
    except Exception as e:
        # Releasing the reserved slot here is essential: without it a failed
        # thread spawn would leave `running` latched on and every subsequent
        # run would 409 until the process restarted.
        progress.finish(error=f"Could not start pipeline thread: {e}")
        raise


@app.post("/api/run")
def execute_pipeline():
    """Starts the full multi-agent pipeline as a background job.

    Returns immediately; poll GET /api/run/progress for status and
    GET /api/employees once it reports done.
    """
    # Atomic reservation -- a check-then-start pattern would let concurrent
    # requests (double-click, two tabs) each launch a run against the same
    # memory files.
    if not progress.try_start("main"):
        raise HTTPException(
            status_code=409, detail="A pipeline run is already in progress."
        )
    _run_pipeline_in_background("main", WEEKLY_DIR, MEMORY_DIR, "engagement_report.txt")
    return {"success": True, "message": "Pipeline started.", "started": True}


@app.post("/api/run/realtime")
def execute_realtime_pipeline():
    """Starts the pipeline for real-time data as a background job. Returns
    immediately; poll GET /api/run/progress for status."""
    # Directories first: idempotent, and doing them before reserving the slot
    # means a filesystem error can't leave the run flag stuck on.
    os.makedirs(REALTIME_DIR, exist_ok=True)
    os.makedirs(REALTIME_MEMORY_DIR, exist_ok=True)
    if not progress.try_start("realtime"):
        raise HTTPException(
            status_code=409, detail="A pipeline run is already in progress."
        )
    _run_pipeline_in_background(
        "realtime", REALTIME_DIR, REALTIME_MEMORY_DIR, "realtime_engagement_report.txt"
    )
    return {"success": True, "message": "Real-time pipeline started.", "started": True}


@app.get("/api/run/progress")
def get_run_progress():
    """Returns the current pipeline run's progress: {running, scope, done, total, current, error}."""
    return progress.snapshot()


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
                "signals": latest_status.get("signals", []),
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


@app.get("/api/employees/realtime")
def get_realtime_employees_status():
    """Loads all real-time employees' final classifications and metrics based on real-time memory files."""
    if not os.path.exists(REALTIME_MEMORY_DIR):
        return []

    memory_files = glob.glob(os.path.join(REALTIME_MEMORY_DIR, "*.json"))
    records = {}

    for path in memory_files:
        filename = os.path.basename(path)
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

    summary = []
    for name, weeks_data in records.items():
        if not weeks_data:
            continue
        latest_week = max(weeks_data.keys())
        latest_status = weeks_data[latest_week]

        summary.append(
            {
                "name": name,
                "score": latest_status.get("score", 1),
                "classification": latest_status.get("classification", "Healthy"),
                "rationale": latest_status.get("rationale", ""),
                "latest_week": latest_week,
                "signals": latest_status.get("signals", []),
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

    summary.sort(key=lambda x: x["name"])
    return summary


@app.get("/api/employee/{name}/briefing")
def get_employee_briefing(name: str, scope: str = "main"):
    """Loads the manager briefing card contents from the employee's latest memory file."""
    name_lower = name.strip().lower()
    target_dir = REALTIME_MEMORY_DIR if scope == "realtime" else MEMORY_DIR
    pattern = os.path.join(target_dir, f"{name_lower}_week*.json")
    memory_files = glob.glob(pattern)

    if not memory_files:
        return {
            "found": False,
            "briefing": "No individual briefing card found for this employee.",
        }

    # Get the latest week file
    latest_file = max(
        memory_files,
        key=lambda x: int(
            os.path.basename(x).replace(f"{name_lower}_week", "").replace(".json", "")
        ),
    )

    try:
        with open(latest_file, encoding="utf-8") as f:
            data = json.load(f)

        if data.get("briefing"):
            return {
                "found": True,
                "briefing": data["briefing"],
                "raw_card": data["briefing"],
            }
        else:
            return {
                "found": False,
                "briefing": "No individual briefing card found for this employee.",
                "raw_card": "",
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


@app.get("/api/report/threat-model")
def get_threat_model():
    """Serves the security THREAT_MODEL.md file content."""
    threat_model_path = "THREAT_MODEL.md"
    if os.path.exists(threat_model_path):
        return FileResponse(threat_model_path, media_type="text/markdown")
    raise HTTPException(status_code=404, detail="Threat model file not found.")


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

        log_event("reset", "main", "Main cohort memory and report cleared.")
        return {"success": True, "message": "All pipeline data and memory cleared."}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to clear memory: {e!s}"
        ) from e


@app.get("/api/report/realtime")
def get_realtime_report():
    """Serves the raw generated realtime_engagement_report.txt file."""
    report_path = "realtime_engagement_report.txt"
    if os.path.exists(report_path):
        return FileResponse(report_path, media_type="text/plain")
    raise HTTPException(
        status_code=404, detail="Real-time engagement report file not found."
    )


@app.post("/api/memory/clear/realtime")
def clear_realtime_data():
    """Deletes all real-time memory JSON files and the real-time engagement report."""
    try:
        if os.path.exists(REALTIME_MEMORY_DIR):
            files = glob.glob(os.path.join(REALTIME_MEMORY_DIR, "*.json"))
            for f in files:
                os.remove(f)
        if os.path.exists(REALTIME_DIR):
            files = glob.glob(os.path.join(REALTIME_DIR, "*.csv"))
            for f in files:
                os.remove(f)
        report_path = "realtime_engagement_report.txt"
        if os.path.exists(report_path):
            os.remove(report_path)
        log_event("reset", "realtime", "Real-time cohort memory and CSVs cleared.")
        return {"success": True, "message": "Real-time data and memory cleared."}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to clear real-time data: {e!s}"
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
                        "sentiment",
                    ]
                )
                for emp in employees:
                    profile = emp_profiles[emp]
                    if profile == "Silent Exit":
                        # Gradual disengagement collapse with random variance
                        tasks = max(1, 10 - int(w * 2.5) + random.randint(-1, 1))
                        resp = round(
                            max(0.5, 0.4 + w * 1.2 + random.uniform(-0.4, 0.6)), 2
                        )
                        after = random.randint(1, max(1, w))
                        sick = random.randint(0, max(0, w - 2))
                        hours = max(35, 45 - (w * 2) + random.randint(-2, 2))
                        acc = max(70, 98 - (w * 5) + random.randint(-5, 5))
                        sent = (
                            random.choice(["Negative", "Neutral"])
                            if w > 2
                            else "Neutral"
                        )
                    elif profile == "At Risk":
                        # Moderate disengagement trend
                        tasks = max(2, 10 - int(w * 1.5) + random.randint(-2, 1))
                        resp = round(
                            max(0.4, 0.5 + w * 0.6 + random.uniform(-0.2, 0.4)), 2
                        )
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

                    writer.writerow(
                        [emp, int(tasks), resp, after, sick, int(hours), int(acc), sent]
                    )

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
                            rat_val = "Severe disengagement flags. Consecutive drop in productivity and communication latency spikes."

                        # Simulate pre-detected signals list for memory file parity
                        mock_signals = []
                        if tasks < 7:
                            mock_signals.append(
                                {
                                    "signal_name": "Declining Task Completion",
                                    "weeks_detected": [w],
                                    "severity": "medium" if tasks >= 4 else "high",
                                }
                            )
                        if resp > 1.5:
                            mock_signals.append(
                                {
                                    "signal_name": "Response Time Spike",
                                    "weeks_detected": [w],
                                    "severity": "high" if resp > 2.2 else "medium",
                                }
                            )
                        if after > 2:
                            mock_signals.append(
                                {
                                    "signal_name": "Sustained Workload Elevation",
                                    "weeks_detected": [w],
                                    "severity": "medium",
                                }
                            )
                        # Sick-day and quality signals removed in Phase 0:
                        # prohibited by config/data_allowlist.json.

                        mock_memory = {
                            "score": sc,
                            "classification": cls_val,
                            "rationale": rat_val,
                            "healthy_streak": w if sc <= 2 else 0,
                            "signals": mock_signals,
                        }
                        mem_path = os.path.join(
                            MEMORY_DIR, f"{emp.lower()}_week{w}.json"
                        )
                        with open(mem_path, "w", encoding="utf-8") as mf:
                            json.dump(mock_memory, mf, indent=2)

        log_event("mock_data", "main", "Generated randomized weekly CSV logs.")
        return {
            "success": True,
            "message": "Successfully generated new randomized weekly metric logs.",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate mock data: {e!s}"
        ) from e


class RawCSVInput(BaseModel):
    week_number: int = Field(ge=MIN_WEEK, le=MAX_WEEK)
    csv_content: str = Field(min_length=1, max_length=2_000_000)


@app.post("/api/ingest/raw")
def ingest_raw_csv(data: RawCSVInput):
    """Ingests pasted raw CSV content, normalizing arbitrary headers via fuzzy
    alias resolution and merging into the target week's file by employee name
    (re-pasting the same employee for a week replaces their row rather than
    duplicating it).

    If the pasted content itself has a week/week_number column, each row is
    routed to its own week automatically -- a single paste can cover an
    entire multi-week export, not just one week at a time.
    """
    try:
        os.makedirs(REALTIME_DIR, exist_ok=True)

        reader = csv.DictReader(io.StringIO(data.csv_content.strip()))
        raw_rows = list(reader)
        if not raw_rows:
            raise HTTPException(
                status_code=400, detail="No data rows found in pasted CSV content."
            )

        grouped = group_rows_by_week(raw_rows, data.week_number)
        total_rows = 0
        for week_num, week_rows in grouped.items():
            canonical_rows = [normalize_row_to_canonical(r) for r in week_rows]
            file_path = os.path.join(REALTIME_DIR, f"week{week_num}.csv")
            merge_rows_into_weekly_csv(file_path, canonical_rows)
            total_rows += len(canonical_rows)

        weeks_msg = (
            f"week {data.week_number}"
            if len(grouped) == 1
            else f"{len(grouped)} weeks ({', '.join(str(w) for w in sorted(grouped))})"
        )
        log_event("ingest", "csv_paste", f"{total_rows} row(s) across {weeks_msg}.")
        return {
            "success": True,
            "message": f"Raw CSV ingested ({total_rows} row(s) across {weeks_msg}).",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to save raw CSV: {e!s}"
        ) from e


class CustomEvaluatorInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    week_number: int = Field(ge=MIN_WEEK, le=MAX_WEEK)
    tasks_completed: int = Field(ge=0, le=1000)
    avg_response_time: float = Field(ge=0, le=1000)
    after_hours_logins: int = Field(ge=0, le=100)
    sick_days: int = Field(ge=0, le=7)
    previous_classification: str = Field(default="Healthy", max_length=50)
    consecutive_weeks_elevated: int = Field(default=0, ge=0, le=1000)
    weekly_hours: int = Field(default=40, ge=0, le=168)
    task_accuracy: int = Field(default=95, ge=0, le=100)
    sentiment: str = Field(default="Neutral", max_length=50)


@app.post("/api/score/custom")
def score_custom_employee(data: CustomEvaluatorInput):
    """Evaluates a single custom employee metrics record in memory, running risk scorer and briefing agents."""
    try:
        from src.manager_briefing_agent import generate_briefing
        from src.risk_scorer_agent import score_risk
        from src.trend_detector_agent import detect_trends

        name = first_name_of(data.name.strip()).capitalize()
        name_lower = name.lower()

        # The simulator uses an isolated scratch directory so a mocked
        # "what-if" run never overwrites a real cohort employee's memory
        # files in MEMORY_DIR (e.g. the default simulator name "Divya" is
        # also a real employee in the main cohort).
        os.makedirs(SIMULATOR_MEMORY_DIR, exist_ok=True)
        for stale in glob.glob(
            os.path.join(SIMULATOR_MEMORY_DIR, f"{name_lower}_week*.json")
        ):
            os.remove(stale)

        # 1. Synthesize mock history file for memory load if provided
        if data.previous_classification != "Healthy":
            # Write mock history files for the preceding weeks based on consecutive_weeks_elevated
            weeks_to_mock = max(1, data.consecutive_weeks_elevated)
            for i in range(weeks_to_mock):
                prev_week = data.week_number - 1 - i
                if prev_week > 0:
                    mock_hist = {
                        "score": (
                            6
                            if data.previous_classification == "At Risk"
                            else (
                                8
                                if data.previous_classification == "Silent Exit"
                                else 4
                            )
                        ),
                        "classification": data.previous_classification,
                        "rationale": "Mocked historical classification.",
                        "healthy_streak": 0,
                    }
                    hist_path = os.path.join(
                        SIMULATOR_MEMORY_DIR, f"{name_lower}_week{prev_week}.json"
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

        # Run Risk Scorer (isolated scratch memory dir -- never touches real cohort data)
        risk_data = score_risk(
            name, signals, data.week_number, memory_dir=SIMULATOR_MEMORY_DIR
        )

        # Run Briefing
        briefing = generate_briefing(
            name, signals, risk_data, memory_dir=SIMULATOR_MEMORY_DIR
        )

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
    db_url: str = Field(default="", max_length=500)
    table_name: str = Field(default="", max_length=100)
    target_week: int = Field(ge=1, le=1000)


class S3SyncInput(BaseModel):
    s3_uri: str = Field(min_length=1, max_length=500)
    target_week: int = Field(ge=1, le=1000)


@app.post("/api/ingest/db")
def ingest_from_db(data: DatabaseSyncInput):
    """Ingests data from a real local SQLite database (data/engagement.db).

    `table_name` is treated as a data value in a parameterized query, never
    interpolated into SQL, so it never needs sanitizing. There is no real
    corporate Postgres server behind this -- it is a genuine local database
    with real persistence, seeded with a demo batch on each sync.
    """
    try:
        table_name = (data.table_name or "weekly_metrics").strip()[:100]
        rows = seed_sample_corporate_batch(table_name, data.target_week)

        os.makedirs(REALTIME_DIR, exist_ok=True)
        file_path = os.path.join(REALTIME_DIR, f"week{data.target_week}.csv")
        canonical_rows = [normalize_row_to_canonical(r) for r in rows]
        merge_rows_into_weekly_csv(file_path, canonical_rows)

        log_event(
            "ingest",
            "sqlite_db",
            f"{len(rows)} record(s) from table '{table_name}' for week {data.target_week}.",
        )
        return {
            "success": True,
            "message": (
                f"Synchronized {len(rows)} employee record(s) from local SQLite "
                f"table '{table_name}' for Week {data.target_week}."
            ),
            "source": "sqlite",
            "db_stats": db_stats(),
        }
    except Exception as e:
        log_event("ingest", "sqlite_db", str(e), success=False)
        raise HTTPException(
            status_code=500, detail=f"Database synchronization failed: {e!s}"
        ) from e


@app.get("/api/ingest/db/status")
def get_db_status():
    """Reports real, persisted stats from the local SQLite database."""
    return db_stats()


@app.post("/api/ingest/s3")
def ingest_from_s3(data: S3SyncInput):
    """Ingests data from an S3 URI.

    Attempts a genuine boto3 S3 GetObject when AWS credentials are present
    in the environment. Otherwise falls back to a real local folder
    (data/s3_bucket/) that mirrors the S3 key layout -- dropping an actual
    CSV file there and syncing genuinely reads that file.
    """
    try:
        rows, source = fetch_object(data.s3_uri, data.target_week)
        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for '{data.s3_uri}' (local bucket or S3).",
            )

        os.makedirs(REALTIME_DIR, exist_ok=True)
        file_path = os.path.join(REALTIME_DIR, f"week{data.target_week}.csv")
        canonical_rows = [normalize_row_to_canonical(r) for r in rows]
        merge_rows_into_weekly_csv(file_path, canonical_rows)

        source_label = {
            "aws-s3": "a live AWS S3 GetObject",
            "local-bucket": "the local bucket folder (data/s3_bucket/)",
            "local-bucket-seeded": "a newly seeded demo object in the local bucket folder",
        }.get(source, source)

        log_event(
            "ingest",
            "cloud_bucket",
            f"{len(rows)} record(s) via {source} for week {data.target_week}.",
        )
        return {
            "success": True,
            "message": (
                f"Synchronized {len(rows)} record(s) from '{data.s3_uri}' via "
                f"{source_label} for Week {data.target_week}."
            ),
            "source": source,
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Cloud download failed: {e!s}"
        ) from e


@app.get("/api/ingest/s3/status")
def get_bucket_status():
    """Reports real, persisted stats from the local bucket folder (data/s3_bucket/)."""
    return bucket_stats()


def extract_json_block(text: str) -> str:
    """Helper to extract JSON object safely from text that contains explanations or code fences."""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return text[start : end + 1]
    return text


class NaturalLanguageInput(BaseModel):
    week_number: int = Field(ge=MIN_WEEK, le=MAX_WEEK)
    text_prompt: str = Field(min_length=1, max_length=5000)


@app.post("/api/ingest/natural-language")
def ingest_natural_language(data: NaturalLanguageInput):
    """Parses a natural language prompt to extract metrics and saves it as a CSV record.

    Tries the Gemini extractor_agent first. If the LLM call fails (quota,
    network, invalid key), falls back to a local regex/keyword extractor
    (src/app_utils/local_nl_extract.py) so natural-language ingestion keeps
    working entirely offline, rather than surfacing a 500 error.
    """
    source = "llm"
    try:
        raw_json_str = run_agent_sync(
            extractor_agent,
            user_id="admin",
            session_id=f"session_extract_{random.randint(1000, 9999)}",
            prompt=data.text_prompt,
        )
        clean_str = extract_json_block(raw_json_str)
        extracted = json.loads(clean_str.strip())
    except Exception:
        logging.getLogger(__name__).warning(
            "LLM extractor_agent unavailable -- using local rule-based fallback."
        )
        source = "local-fallback"
        extracted = extract_metrics_from_text(data.text_prompt)

    try:
        name = str(extracted.get("employee_name", "Unknown")).strip().capitalize()
        tasks = int(extracted.get("tasks_completed", 0))
        resp = float(extracted.get("avg_response_time_hours", 0.0))
        after = int(extracted.get("after_hours_logins", 0))
        sick = int(extracted.get("sick_days", 0))
        hours = int(extracted.get("weekly_hours", random.randint(35, 45)))
        acc = int(extracted.get("task_accuracy", random.randint(85, 100)))
        sent = (
            str(
                extracted.get(
                    "sentiment", random.choice(["Positive", "Neutral", "Negative"])
                )
            )
            .strip()
            .capitalize()
        )

        os.makedirs(REALTIME_DIR, exist_ok=True)
        file_path = os.path.join(REALTIME_DIR, f"week{data.week_number}.csv")
        merge_rows_into_weekly_csv(
            file_path, [[name, tasks, resp, after, sick, hours, acc, sent]]
        )

        log_event(
            "ingest",
            "natural_language",
            f"Extracted {name} for week {data.week_number} (source: {source}).",
        )
        return {
            "success": True,
            "source": source,
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


@app.post("/api/ingest/upload")
async def ingest_uploaded_csv(
    # Bounded to match every other ingestion endpoint. Previously a bare
    # Form(...) with no range, so a week of 0 or -5 reached the filesystem and
    # the baseline-relative scorer.
    week_number: int = Form(..., ge=MIN_WEEK, le=MAX_WEEK),
    file: UploadFile = File(...),  # noqa: B008
):
    """Ingests a real uploaded CSV file (multipart/form-data), normalizing its
    headers via fuzzy alias resolution and merging its rows into the target
    week's file by employee name.

    If the file itself has a week/week_number column, each row is routed to
    its own week automatically -- a single upload can cover a full
    multi-week export, not just one week at a time.
    """
    try:
        if not file.filename.lower().endswith(".csv"):
            raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

        # Read one byte past the limit so we can tell "exactly at the limit"
        # apart from "too large" without ever buffering more than necessary.
        raw_bytes = await file.read(MAX_UPLOAD_SIZE_BYTES + 1)
        if len(raw_bytes) > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File too large (max {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB).",
            )
        text = raw_bytes.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        raw_rows = list(reader)
        if not raw_rows:
            raise HTTPException(
                status_code=400, detail="Uploaded CSV contained no data rows."
            )

        os.makedirs(REALTIME_DIR, exist_ok=True)
        grouped = group_rows_by_week(raw_rows, week_number)
        total_rows = 0
        for week_num, week_rows in grouped.items():
            canonical_rows = [normalize_row_to_canonical(r) for r in week_rows]
            file_path = os.path.join(REALTIME_DIR, f"week{week_num}.csv")
            merge_rows_into_weekly_csv(file_path, canonical_rows)
            total_rows += len(canonical_rows)

        weeks_msg = (
            f"week {week_number}"
            if len(grouped) == 1
            else f"{len(grouped)} weeks ({', '.join(str(w) for w in sorted(grouped))})"
        )
        log_event(
            "ingest",
            "file_upload",
            f"'{file.filename}': {total_rows} row(s) across {weeks_msg}.",
        )
        return {
            "success": True,
            "message": f"Uploaded file '{file.filename}' ingested ({total_rows} row(s) across {weeks_msg}).",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"File upload ingestion failed: {e!s}"
        ) from e


class WebhookMetricRecord(BaseModel):
    employee_name: str = Field(min_length=1, max_length=100)
    week_number: int | None = Field(
        default=None, ge=MIN_WEEK, le=MAX_WEEK
    )  # overrides the payload-level week_number when set
    tasks_completed: int = Field(default=0, ge=0, le=1000)
    avg_response_time_hours: float = Field(default=0.0, ge=0, le=1000)
    after_hours_logins: int = Field(default=0, ge=0, le=100)
    sick_days: int = Field(default=0, ge=0, le=7)
    weekly_hours: int = Field(default=40, ge=0, le=168)
    task_accuracy: int = Field(default=95, ge=0, le=100)
    sentiment: str = Field(default="Neutral", max_length=50)


class WebhookIngestInput(BaseModel):
    week_number: int = Field(ge=MIN_WEEK, le=MAX_WEEK)
    records: list[WebhookMetricRecord] = Field(min_length=1, max_length=500)


@app.post("/api/ingest/webhook")
def ingest_webhook(data: WebhookIngestInput):
    """Accepts a structured JSON payload of employee metric records -- the
    integration point for an external HR system, a Zapier/Slack bot, or any
    service that can POST JSON -- and merges them into the target week by
    employee name. A record may set its own week_number to override the
    payload-level default, so one webhook call can span multiple weeks."""
    try:
        by_week: dict[int, list[list]] = {}
        for r in data.records:
            week_num = r.week_number if r.week_number is not None else data.week_number
            by_week.setdefault(week_num, []).append(
                [
                    r.employee_name,
                    r.tasks_completed,
                    r.avg_response_time_hours,
                    r.after_hours_logins,
                    r.sick_days,
                    r.weekly_hours,
                    r.task_accuracy,
                    r.sentiment,
                ]
            )

        os.makedirs(REALTIME_DIR, exist_ok=True)
        total_rows = 0
        for week_num, rows in by_week.items():
            file_path = os.path.join(REALTIME_DIR, f"week{week_num}.csv")
            merge_rows_into_weekly_csv(file_path, rows)
            total_rows += len(rows)

        weeks_msg = (
            f"week {data.week_number}"
            if len(by_week) == 1
            else f"{len(by_week)} weeks ({', '.join(str(w) for w in sorted(by_week))})"
        )
        log_event("ingest", "webhook", f"{total_rows} record(s) across {weeks_msg}.")
        return {
            "success": True,
            "message": f"Webhook ingested {total_rows} record(s) across {weeks_msg}.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Webhook ingestion failed: {e!s}"
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
