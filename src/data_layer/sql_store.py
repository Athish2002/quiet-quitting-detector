# src/data_layer/sql_store.py
# Real local SQLite-backed "corporate database" ingestion source.
#
# This replaces a purely cosmetic simulation (hardcoded rows appended to a
# CSV on every click) with genuine persistence: rows are actually INSERTed
# into and SELECTed back out of a SQLite file on disk (data/engagement.db),
# via parameterized queries only. `table_name` is user-supplied but is never
# interpolated into SQL -- it is stored and filtered as ordinary data, which
# avoids SQL injection without needing to validate/allowlist identifiers.
#
# It is still a demo dataset (there is no real corporate Postgres server
# behind it), so the UI must label it honestly as a local SQLite database,
# not as a live production connection.

import os
import random
import sqlite3
from datetime import UTC, datetime

DB_PATH = os.path.join("data", "engagement.db")

# Sample "corporate" employees distinct from the CSV cohort, so a DB sync
# clearly adds new records rather than duplicating/colliding with names
# already present in data/weekly/*.csv.
_SAMPLE_EMPLOYEES = ["Rohan", "Sneha", "Vikram", "Ananya", "Karan", "Neha"]
_SENTIMENTS = ["Positive", "Neutral", "Constructive"]


def _connect(db_path: str = DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(db_path: str = DB_PATH) -> None:
    """Create the weekly_metrics table if it does not already exist."""
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weekly_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_name TEXT NOT NULL,
                week_number INTEGER NOT NULL,
                employee_name TEXT NOT NULL,
                tasks_completed INTEGER,
                avg_response_time_hours REAL,
                after_hours_logins INTEGER,
                sick_days INTEGER,
                weekly_hours INTEGER,
                task_accuracy INTEGER,
                sentiment TEXT,
                ingested_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def insert_rows(
    rows: list[dict], table_name: str, week_number: int, db_path: str = DB_PATH
) -> int:
    """Insert rows into the real SQLite table via parameterized queries.

    Each row dict must contain the canonical metric keys (employee_name,
    tasks_completed, avg_response_time_hours, after_hours_logins, sick_days,
    weekly_hours, task_accuracy, sentiment).
    """
    ensure_schema(db_path)
    now = datetime.now(UTC).isoformat()
    with _connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO weekly_metrics (
                table_name, week_number, employee_name, tasks_completed,
                avg_response_time_hours, after_hours_logins, sick_days,
                weekly_hours, task_accuracy, sentiment, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    table_name,
                    week_number,
                    r["employee_name"],
                    r.get("tasks_completed"),
                    r.get("avg_response_time_hours"),
                    r.get("after_hours_logins"),
                    r.get("sick_days"),
                    r.get("weekly_hours"),
                    r.get("task_accuracy"),
                    r.get("sentiment"),
                    now,
                )
                for r in rows
            ],
        )
        conn.commit()
    return len(rows)


def seed_sample_corporate_batch(
    table_name: str, week_number: int, db_path: str = DB_PATH
) -> list[dict]:
    """Generate and persist a small randomized batch of demo corporate rows.

    Returns the rows that were inserted (for the caller to also merge into
    the pipeline's weekly CSV).
    """
    picked = random.sample(_SAMPLE_EMPLOYEES, k=random.randint(2, 3))
    rows = []
    for name in picked:
        rows.append(
            {
                "employee_name": name,
                "tasks_completed": random.randint(7, 11),
                "avg_response_time_hours": round(random.uniform(0.3, 1.2), 2),
                "after_hours_logins": random.randint(0, 2),
                "sick_days": random.randint(0, 1),
                "weekly_hours": random.randint(36, 44),
                "task_accuracy": random.randint(88, 99),
                "sentiment": random.choice(_SENTIMENTS),
            }
        )
    insert_rows(rows, table_name, week_number, db_path)
    return rows


def fetch_rows(table_name: str, week_number: int, db_path: str = DB_PATH) -> list[dict]:
    """Select back all rows for a given (table_name, week_number) via a
    parameterized query -- table_name is data here, never a SQL identifier."""
    ensure_schema(db_path)
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT employee_name, tasks_completed, avg_response_time_hours,
                   after_hours_logins, sick_days, weekly_hours, task_accuracy,
                   sentiment
            FROM weekly_metrics
            WHERE table_name = ? AND week_number = ?
            ORDER BY id
            """,
            (table_name, week_number),
        )
        return [dict(row) for row in cursor.fetchall()]


def db_stats(db_path: str = DB_PATH) -> dict:
    """Return a small summary of the real persisted state, for the UI."""
    if not os.path.exists(db_path):
        return {
            "exists": False,
            "total_rows": 0,
            "distinct_tables": 0,
            "distinct_weeks": 0,
            "file_size_bytes": 0,
        }
    ensure_schema(db_path)
    with _connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM weekly_metrics").fetchone()["c"]
        tables = conn.execute(
            "SELECT COUNT(DISTINCT table_name) AS c FROM weekly_metrics"
        ).fetchone()["c"]
        weeks = conn.execute(
            "SELECT COUNT(DISTINCT week_number) AS c FROM weekly_metrics"
        ).fetchone()["c"]
        latest = conn.execute(
            "SELECT MAX(ingested_at) AS t FROM weekly_metrics"
        ).fetchone()["t"]
    return {
        "exists": True,
        "total_rows": total,
        "distinct_tables": tables,
        "distinct_weeks": weeks,
        "file_size_bytes": os.path.getsize(db_path),
        "last_ingested_at": latest,
    }
