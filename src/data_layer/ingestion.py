# src/data_layer/ingestion.py
# Ingestion layer for discovering and loading raw weekly CSV files.

import csv
import glob
import logging
import os

logger = logging.getLogger(__name__)

# List of aliases for fuzzy mapping of metric keys to CSV header names
COLUMN_ALIASES = {
    "name": [
        "employee_name",
        "name",
        "first_name",
        "employee",
        "username",
        "user",
        "first name",
        "employee name",
    ],
    "tasks_completed": [
        "tasks_completed",
        "completed_tasks",
        "tasks",
        "completed",
        "task_count",
        "tasks completed",
        "completed tasks",
    ],
    "avg_response_time": [
        "avg_response_time_hours",
        "response_time",
        "avg_response_time",
        "response_time_hours",
        "latency",
        "average response time",
        "response time",
    ],
    "after_hours_logins": [
        "after_hours_logins",
        "after_hours",
        "logins",
        "after hours logins",
        "night_logins",
        "after-hours",
        "afterhours",
    ],
    "sick_days": [
        "sick_days",
        "sick_leaves",
        "sick",
        "absences",
        "sick days",
        "leaves",
        "absent",
    ],
    "weekly_hours": [
        "weekly_hours",
        "hours_worked",
        "hours",
        "weekly hours",
        "work hours",
        "logged_hours",
    ],
    "task_accuracy": [
        "task_accuracy",
        "accuracy",
        "quality",
        "accuracy_score",
        "task accuracy",
        "quality_score",
    ],
    "sentiment": [
        "sentiment",
        "tone",
        "response_tone",
        "attitude",
        "communication_sentiment",
        "morale",
    ],
}


def resolve_header_value(row: dict, aliases: list[str], default: str = "") -> str:
    """Finds a column in the row matching any of the alias patterns (fuzzy match) and returns its value."""
    headers = list(row.keys())

    # 1. Exact match (case-insensitive, ignoring spacing/delimiters)
    for h in headers:
        if not h:
            continue
        h_clean = h.strip().lower().replace("_", "").replace("-", "").replace(" ", "")
        for alias in aliases:
            alias_clean = (
                alias.strip().lower().replace("_", "").replace("-", "").replace(" ", "")
            )
            if h_clean == alias_clean:
                return row.get(h) or default

    # 2. Substring match
    for h in headers:
        if not h:
            continue
        h_clean = h.strip().lower()

        # Targeted exclusion: prevent after_hours columns from matching weekly_hours
        if "after" in h_clean and ("hours" in aliases or "weekly_hours" in aliases):
            continue

        for alias in aliases:
            alias_clean = alias.strip().lower()
            if alias_clean in h_clean or h_clean in alias_clean:
                return row.get(h) or default

    return default


def ingest_weekly_csvs(folder_path: str) -> list[dict]:
    """Ingests all CSV files in the folder and returns a list of raw parsed rows with parsed week numbers."""
    if not os.path.exists(folder_path):
        logger.error("Folder path %s does not exist", folder_path)
        return []

    csv_files = glob.glob(os.path.join(folder_path, "*.csv"))
    if not csv_files:
        logger.warning("No CSV files found in %s", folder_path)
        return []

    # Sort files chronologically
    csv_files.sort()

    all_raw_data = []

    for file_path in csv_files:
        if not os.path.exists(file_path):
            continue

        filename = os.path.basename(file_path)

        # Parse week number from filename (e.g. week1.csv -> 1)
        week_num = 1
        try:
            name_part = os.path.splitext(filename)[0]
            week_num = int("".join(filter(str.isdigit, name_part)))
        except ValueError:
            logger.warning(
                "Could not extract week number from filename: %s, defaulting to 1",
                filename,
            )

        try:
            with open(file_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row["__week_number__"] = week_num
                    row["__source_file__"] = filename
                    all_raw_data.append(row)
        except Exception as e:
            logger.error("Error reading CSV file %s: %s", file_path, e)

    return all_raw_data
