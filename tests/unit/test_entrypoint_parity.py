# Both entrypoints must share one governed preprocessing path.
#
# `run_pipeline.py` (CLI) previously carried its own inline CSV parsing, so the
# Phase 0 controls -- default-deny allowlist, identity resolution, missing-value
# semantics -- applied only to `app.py`. On that path `sick_days` (health data,
# prohibited by config/data_allowlist.json and CONTEXT.md rule 6) was still read,
# identity was still keyed on first name, and an absent metric still became 0.
#
# These tests fail if that duplication returns.

import csv

import pytest

PROHIBITED = ("sick_days", "task_accuracy", "sentiment")


@pytest.fixture(autouse=True)
def _isolated_identity(tmp_path, monkeypatch):
    from src.data_layer import identity

    monkeypatch.setenv("IDENTITY_MAP_PATH", str(tmp_path / "idmap.json"))
    monkeypatch.setenv("IDENTITY_SALT", "test-salt-not-a-secret")
    identity.reset_resolver()
    yield
    identity.reset_resolver()


def _write_week(path, rows, header):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def test_cli_delegates_to_shared_preprocessing():
    """The CLI must not reimplement parsing. Guards against re-duplication."""
    import inspect

    import run_pipeline

    source = inspect.getsource(run_pipeline._load_all_weeks)
    assert "preprocess_employee_records" in source, (
        "run_pipeline must call the shared preprocessing, not its own parser"
    )
    for banned in PROHIBITED:
        assert banned not in source or "prohibited" in source, (
            f"{banned} must not be parsed in the CLI path"
        )


def test_cli_output_carries_no_prohibited_fields(tmp_path):
    """A legacy CSV still containing the columns must not leak them through."""
    import run_pipeline

    header = [
        "employee_name",
        "tasks_completed",
        "avg_response_time_hours",
        "after_hours_logins",
        "sick_days",
        "weekly_hours",
        "task_accuracy",
        "sentiment",
    ]
    _write_week(
        tmp_path / "week1.csv",
        [
            {
                "employee_name": "Ada Lovelace",
                "tasks_completed": "8",
                "avg_response_time_hours": "1.2",
                "after_hours_logins": "1",
                "sick_days": "3",
                "weekly_hours": "40",
                "task_accuracy": "61",
                "sentiment": "Withdrawn",
            }
        ],
        header,
    )

    records, _ = run_pipeline._load_all_weeks(str(tmp_path))
    week = next(iter(records.values()))[0]

    for banned in PROHIBITED:
        assert banned not in week, f"{banned} reached the CLI timeline"
    assert "3" not in str(week.values()) or week.get("after_hours_logins") is not None


def test_cli_applies_identity_resolution_and_quality(tmp_path):
    """Governance markers prove the shared path ran, not a private copy."""
    import run_pipeline

    header = ["employee_name", "tasks_completed", "weekly_hours"]
    _write_week(
        tmp_path / "week1.csv",
        [
            {
                "employee_name": "Ada Lovelace",
                "tasks_completed": "8",
                "weekly_hours": "40",
            }
        ],
        header,
    )
    records, _ = run_pipeline._load_all_weeks(str(tmp_path))
    week = next(iter(records.values()))[0]

    assert week["surrogate_id"].startswith("emp_")
    assert "data_quality" in week


def test_cli_does_not_fabricate_missing_metrics(tmp_path):
    """Absent metrics stay None rather than becoming a real-looking zero."""
    import run_pipeline

    _write_week(
        tmp_path / "week1.csv",
        [{"employee_name": "Ada Lovelace"}],
        ["employee_name"],
    )
    records, _ = run_pipeline._load_all_weeks(str(tmp_path))
    week = next(iter(records.values()))[0]

    assert week["completed_tasks"] is None
    assert week["weekly_hours"] is None
    assert week["data_quality"]["low_confidence"] is True


def test_mock_generator_emits_only_canonical_columns():
    """The generator previously re-created prohibited columns on every run."""
    import inspect

    from src.api.routers import simulator
    from src.data_layer.ingestion import CANONICAL_HEADER

    # Moved out of app.py by the Phase 5 restructure. Inspecting the whole
    # module rather than one function: the generator is several helpers now, and
    # a prohibited column could be reintroduced in any of them.
    source = inspect.getsource(simulator)
    for banned in PROHIBITED:
        assert f'"{banned}"' not in source, f"mock generator still writes {banned}"
    assert "CANONICAL_HEADER" in source
    for banned in PROHIBITED:
        assert banned not in CANONICAL_HEADER
