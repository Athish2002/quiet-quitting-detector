# src/data_layer/ingestion.py
# Ingestion layer for discovering and loading raw weekly CSV files.

import csv
import glob
import logging
import os
import re

logger = logging.getLogger(__name__)

# Valid week-number range, enforced identically at every ingestion entry point
# (paste, upload, DB, bucket, webhook, natural language) and mirrored by the
# Pydantic `Field(ge=..., le=...)` bounds on the request models in app.py.
#
# The lower bound matters for correctness, not just tidiness: trend detection
# baselines every employee against their own **week 1**, so a week <= 0 sorts
# *before* the baseline and is then scored as though it came after it --
# silently corrupting every downstream signal. Unbounded values also let a
# single CSV cell spawn junk artifacts like `week-5.csv` or `week999999999.csv`.
MIN_WEEK = 1
MAX_WEEK = 1000


def is_valid_week(week: int) -> bool:
    """Whether `week` is inside the supported range."""
    return MIN_WEEK <= week <= MAX_WEEK


# Matches "week" (case-insensitive) directly followed by digits, e.g.
# "week4.csv" -> 4, "Week12_2026.csv" -> 12. Falls back to the first run of
# digits in the filename if no "week<N>" token is present.
_WEEK_TOKEN_RE = re.compile(r"week0*(\d+)", re.IGNORECASE)
_FIRST_DIGITS_RE = re.compile(r"\d+")


def parse_week_number(filename: str, default: int = 1) -> int:
    """Extract the week number from a weekly CSV filename.

    Naively concatenating every digit in the filename (the previous
    approach) turns "week1_2026.csv" into 12026. This looks for a
    "week<N>" token first, and only falls back to the first digit run
    found anywhere in the name.
    """
    name_part = os.path.splitext(filename)[0]
    match = _WEEK_TOKEN_RE.search(name_part)
    if match:
        return int(match.group(1))
    match = _FIRST_DIGITS_RE.search(name_part)
    if match:
        return int(match.group(0))
    return default


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
    "weekly_hours": [
        "weekly_hours",
        "hours_worked",
        "hours",
        "weekly hours",
        "work hours",
        "logged_hours",
    ],
}


# Canonical 8-column schema every ingestion source normalizes into before
# being appended to a data/{realtime,weekly}/weekN.csv file. Keeping every
# source (paste, DB, S3, natural-language, upload, webhook) on one shared
# schema means they can all safely append to the same file instead of each
# assuming they own the whole file.
CANONICAL_HEADER = [
    "employee_name",
    "tasks_completed",
    "avg_response_time_hours",
    "after_hours_logins",
    "weekly_hours",
]
# Phase 0 removals -- these are NOT merely unused, they are prohibited by
# config/data_allowlist.json and must never re-enter this schema:
#   sick_days     -- health data (GDPR Art. 9; ADA/FMLA exposure)
#   sentiment     -- emotion inference (EU AI Act Art. 5 prohibited practice)
#   task_accuracy -- performance metric; drags a support tool toward punitive use
# Legacy CSVs still carrying these columns read fine (parsing is header-driven,
# not positional); the extra columns are dropped rather than mapped.

_CANONICAL_DEFAULTS = {
    "name": "Unknown",
    "tasks_completed": "0",
    "avg_response_time": "0.0",
    "after_hours_logins": "0",
    "weekly_hours": "40",
}


def normalize_row_to_canonical(row: dict, *, source: str = "unknown") -> list[str]:
    """Map an arbitrary-header row to the canonical column order.

    This is the data-minimization choke point: every ingestion source funnels
    through here, so applying the allowlist at this single seam guarantees a
    prohibited field cannot reach storage via any connector. Forbidden fields
    are dropped and audited (never silently ignored); unknown fields are
    dropped quietly, since sources add columns all the time.

    `strict=False` so one bad row quarantines rather than aborting an entire
    batch -- the field still never persists either way.
    """
    from src.governance.allowlist import filter_record

    filter_record(row, source=source, strict=False)

    return [
        resolve_header_value(row, COLUMN_ALIASES["name"], _CANONICAL_DEFAULTS["name"]),
        resolve_header_value(
            row,
            COLUMN_ALIASES["tasks_completed"],
            _CANONICAL_DEFAULTS["tasks_completed"],
        ),
        resolve_header_value(
            row,
            COLUMN_ALIASES["avg_response_time"],
            _CANONICAL_DEFAULTS["avg_response_time"],
        ),
        resolve_header_value(
            row,
            COLUMN_ALIASES["after_hours_logins"],
            _CANONICAL_DEFAULTS["after_hours_logins"],
        ),
        resolve_header_value(
            row, COLUMN_ALIASES["weekly_hours"], _CANONICAL_DEFAULTS["weekly_hours"]
        ),
    ]


def merge_rows_into_weekly_csv(file_path: str, rows: list[list[str]]) -> int:
    """Merge normalized rows into a weekly CSV, keyed by employee name.

    Every ingestion source (DB, bucket, paste, upload, webhook, NL) shares
    this instead of blindly appending. A plain append would duplicate an
    employee's row every time the same week is re-synced from a second
    source (or the same source twice) -- preprocess_employee_records()
    assumes one record per employee per week, so a duplicate silently
    corrupts that week's trend detection. Re-ingesting an employee for a
    week that already has a row now replaces it (last write wins); a new
    employee is appended. Returns the resulting total row count.
    """
    existing: dict[str, list[str]] = {}
    order: list[str] = []

    if os.path.exists(file_path):
        with open(file_path, encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            next(reader, None)  # skip header
            for row in reader:
                if not row or not row[0].strip():
                    continue
                key = row[0].strip().lower()
                if key not in existing:
                    order.append(key)
                existing[key] = row

    for row in rows:
        str_row = [str(v) for v in row]
        key = str_row[0].strip().lower()
        if key not in existing:
            order.append(key)
        existing[key] = str_row

    with open(file_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(CANONICAL_HEADER)
        for key in order:
            writer.writerow(existing[key])

    return len(order)


# Aliases for a week-number column embedded directly in an ingested CSV.
WEEK_COLUMN_ALIASES = ["week", "week_number", "week_num", "simulation_week", "wk"]


def group_rows_by_week(
    raw_rows: list[dict], default_week: int
) -> dict[int, list[dict]]:
    """Group raw CSV rows by an embedded week column, if present.

    Lets a single paste/upload cover multiple weeks at once (e.g. a full
    4-week export) instead of forcing every row into one target week --
    each row's own week value (any of WEEK_COLUMN_ALIASES) is honored when
    present; rows without one fall back to `default_week`.

    An embedded week that is missing, non-numeric, or outside
    [MIN_WEEK, MAX_WEEK] falls back to `default_week` (which callers validate)
    rather than being trusted -- see the MIN_WEEK/MAX_WEEK note above for why
    an out-of-range week silently corrupts baseline-relative scoring.
    """
    grouped: dict[int, list[dict]] = {}
    rejected = 0
    for row in raw_rows:
        week_val = resolve_header_value(row, WEEK_COLUMN_ALIASES, "")
        try:
            week = int(week_val) if week_val else default_week
        except ValueError:
            week = default_week
        if not is_valid_week(week):
            rejected += 1
            week = default_week
        grouped.setdefault(week, []).append(row)
    if rejected:
        logger.warning(
            "%d row(s) carried an out-of-range week value (valid: %d-%d); "
            "routed to the request's target week %d instead.",
            rejected,
            MIN_WEEK,
            MAX_WEEK,
            default_week,
        )
    return grouped


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

        # Targeted exclusions: the generic "hours" alias for weekly_hours would
        # otherwise substring-match any other *_hours column -- after_hours
        # columns (already handled) and response/latency columns, since
        # "avg_response_time_hours" contains "hours" too.
        if "after" in h_clean and ("hours" in aliases or "weekly_hours" in aliases):
            continue
        if ("response" in h_clean or "latency" in h_clean) and (
            "hours" in aliases or "weekly_hours" in aliases
        ):
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
        week_num = parse_week_number(filename)

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
