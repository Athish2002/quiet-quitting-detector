# src/data_layer/preprocessing.py
# Preprocessing layer for grouping, converting metrics, and timeline baseline formatting.

import logging

from src.data_layer.ingestion import COLUMN_ALIASES, resolve_header_value

logger = logging.getLogger(__name__)


def preprocess_employee_records(
    raw_rows: list[dict],
) -> tuple[dict[str, list[dict]], int]:
    """Groups raw rows by employee, converts metrics, and determines max week."""
    employee_records = {}
    max_week = 0

    for row in raw_rows:
        week_num = row.get("__week_number__", 1)
        max_week = max(max_week, week_num)

        # Rule 1: First name only
        raw_name = resolve_header_value(row, COLUMN_ALIASES["name"], "Unknown")
        first_name = raw_name.split()[0]

        # Safely convert metrics
        try:
            completed_tasks = int(
                resolve_header_value(row, COLUMN_ALIASES["tasks_completed"], "0")
            )
        except ValueError:
            completed_tasks = 0

        try:
            response_time = float(
                resolve_header_value(row, COLUMN_ALIASES["avg_response_time"], "0.0")
            )
        except ValueError:
            response_time = 0.0

        try:
            after_hours_logins = int(
                resolve_header_value(row, COLUMN_ALIASES["after_hours_logins"], "0")
            )
        except ValueError:
            after_hours_logins = 0

        try:
            sick_days = int(resolve_header_value(row, COLUMN_ALIASES["sick_days"], "0"))
        except ValueError:
            sick_days = 0

        metrics = {
            "week": week_num,
            "completed_tasks": completed_tasks,
            "response_time": response_time,
            "after_hours_logins": after_hours_logins,
            "sick_days": sick_days,
            "source_file": row.get("__source_file__", ""),
        }

        if first_name not in employee_records:
            employee_records[first_name] = []
        employee_records[first_name].append(metrics)

    # Sort each employee's week records chronologically
    for first_name in employee_records:
        employee_records[first_name].sort(key=lambda x: x["week"])

    return employee_records, max_week
