# app.py
# Production-grade FastAPI backend for the Quiet-Quitting Detector dashboard.

import glob
import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from src.orchestrator_agent import run_orchestrator

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
