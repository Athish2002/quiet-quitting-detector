# tests/unit/test_data_layer.py
# Unit tests for the modular data ingestion and preprocessing layers.

from src.data_layer.ingestion import resolve_header_value
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
    assert first_week["sick_days"] == 0
