# tests/unit/test_data_layer.py
# Unit tests for the modular data ingestion and preprocessing layers.

from src.data_layer.ingestion import (
    group_rows_by_week,
    merge_rows_into_weekly_csv,
    normalize_row_to_canonical,
    resolve_header_value,
)
from src.data_layer.preprocessing import preprocess_employee_records


def test_resolve_header_value_exact():
    row = {"employee_name": "Arjun", "tasks_completed": "10"}
    val = resolve_header_value(row, ["employee_name", "name"])
    assert val == "Arjun"


def test_resolve_header_value_fuzzy_case():
    row = {"Name": "Arjun", "Tasks Completed": "10"}
    val = resolve_header_value(row, ["employee_name", "name"])
    assert val == "Arjun"


def test_resolve_header_value_substring():
    row = {"user_first_name_raw": "Arjun"}
    val = resolve_header_value(row, ["first_name", "name"])
    assert val == "Arjun"


def test_resolve_header_value_default():
    row = {"some_other_field": "val"}
    val = resolve_header_value(row, ["name"], "DefaultName")
    assert val == "DefaultName"


def test_preprocess_employee_records():
    raw_rows = [
        {
            "name": "Arjun",
            "completed_tasks": "8",
            "avg_response_time": "1.5",
            "after_hours_logins": "2",
            "sick_days": "0",
            "__week_number__": 1,
            "__source_file__": "week1.csv",
        },
        {
            "name": "Arjun",
            "completed_tasks": "6",
            "avg_response_time": "2.5",
            "after_hours_logins": "1",
            "sick_days": "1",
            "__week_number__": 2,
            "__source_file__": "week2.csv",
        },
    ]

    records, max_week = preprocess_employee_records(raw_rows)
    assert max_week == 2
    assert "Arjun" in records
    assert len(records["Arjun"]) == 2

    first_week = records["Arjun"][0]
    assert first_week["week"] == 1
    assert first_week["completed_tasks"] == 8
    assert first_week["response_time"] == 1.5
    assert first_week["after_hours_logins"] == 2
    assert first_week["weekly_hours"] is None

    # Phase 0: prohibited fields must not survive preprocessing even when the
    # source row still carries them (legacy CSVs do). See config/data_allowlist.json.
    for prohibited in ("sick_days", "task_accuracy", "sentiment"):
        assert prohibited not in first_week


def test_resolve_header_value_does_not_confuse_response_time_with_weekly_hours():
    """Regression test: "avg_response_time_hours" contains "hours" as a
    substring, which used to fuzzy-match the generic "hours" alias for
    weekly_hours when no weekly_hours column was present at all."""
    row = {"avg_response_time_hours": "2.5"}
    val = resolve_header_value(row, ["weekly_hours", "hours_worked", "hours"], "")
    assert val == ""


def test_normalize_row_to_canonical_defaults_weekly_hours_when_absent():
    row = {
        "employee_name": "Test",
        "avg_response_time_hours": "2.5",
        "tasks_completed": "4",
    }
    canonical = normalize_row_to_canonical(row)
    # Canonical order after the Phase 0 removals:
    # [name, tasks, resp, after_hours, weekly_hours]
    assert canonical[4] == "40"  # weekly_hours default, not the 2.5 response time


def test_group_rows_by_week_routes_by_embedded_week_column():
    raw_rows = [
        {"employee_name": "A", "week_number": "1", "tasks_completed": "5"},
        {"employee_name": "B", "week_number": "2", "tasks_completed": "6"},
        {"employee_name": "C", "tasks_completed": "7"},  # no week column
    ]
    grouped = group_rows_by_week(raw_rows, default_week=9)
    assert grouped[1][0]["employee_name"] == "A"
    assert grouped[2][0]["employee_name"] == "B"
    assert grouped[9][0]["employee_name"] == "C"


def test_merge_rows_into_weekly_csv_replaces_by_employee_not_duplicates(tmp_path):
    file_path = tmp_path / "week1.csv"
    merge_rows_into_weekly_csv(
        str(file_path),
        [
            ["Arjun", 8, 1.0, 0, 0, 40, 95, "Neutral"],
            ["Priya", 9, 0.8, 0, 0, 40, 96, "Positive"],
        ],
    )
    merge_rows_into_weekly_csv(
        str(file_path),
        [
            ["Arjun", 3, 3.5, 2, 1, 45, 70, "Negative"],
            ["Karthik", 7, 1.2, 0, 0, 40, 90, "Neutral"],
        ],
    )

    import csv

    with open(file_path, encoding="utf-8") as fh:
        rows = list(csv.reader(fh))

    assert len(rows) == 4  # header + 3 employees, Arjun not duplicated
    arjun_row = next(r for r in rows if r[0] == "Arjun")
    assert arjun_row[1] == "3"  # replaced with the second ingest's values
