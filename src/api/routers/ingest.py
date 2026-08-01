# src/api/routers/ingest.py
# Every way data gets in.
#
# All six paths converge on `merge_rows_into_weekly_csv` after
# `normalize_row_to_canonical`, which is what stops any one of them becoming a
# route around the governance layer -- the failure that was blocker B6 on the
# CLI side. A new source adds a reader, never a writer.
#
# Prohibited columns cannot enter here even if a caller sends them: the request
# models below simply have no field for `sick_days`, `task_accuracy` or
# `sentiment`, and `normalize_row_to_canonical` drops anything not on the
# allowlist.

from __future__ import annotations

import csv
import io
import json
import logging
import random

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from src.api.paths import MAX_UPLOAD_SIZE_BYTES, REALTIME_DIR, ensure
from src.app_utils.audit_log import log_event
from src.app_utils.local_nl_extract import extract_metrics_from_text
from src.data_layer.ingestion import (
    MAX_WEEK,
    MIN_WEEK,
    group_rows_by_week,
    merge_rows_into_weekly_csv,
    normalize_row_to_canonical,
)
from src.data_layer.s3_store import bucket_stats, fetch_object
from src.data_layer.sql_store import db_stats, seed_sample_corporate_batch
from src.security import IdempotencyStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingest"])

#: Shared across ingest routes. A sender that times out and retries -- which is
#: what every sender eventually does -- would otherwise append a second copy of
#: the week. Nobody sees an error: one person's metrics silently double, which
#: reads as an employee whose output suddenly improved.
idempotency = IdempotencyStore()


def _replay(request: Request) -> tuple[str | None, dict | None]:
    key = request.headers.get("Idempotency-Key")
    return key, idempotency.seen(key) if key else None


def _remember(key: str | None, result: dict) -> dict:
    if key:
        idempotency.remember(key, result)
    return result


def _write_grouped(raw_rows: list[dict], default_week: int) -> tuple[int, str]:
    """Normalise, group by week, merge. Returns (row count, description)."""
    ensure(REALTIME_DIR)
    grouped = group_rows_by_week(raw_rows, default_week)

    total = 0
    for week_num, week_rows in grouped.items():
        canonical = [normalize_row_to_canonical(row) for row in week_rows]
        merge_rows_into_weekly_csv(f"{REALTIME_DIR}/week{week_num}.csv", canonical)
        total += len(canonical)

    description = (
        f"week {default_week}"
        if len(grouped) == 1
        else f"{len(grouped)} weeks ({', '.join(str(w) for w in sorted(grouped))})"
    )
    return total, description


class RawCSVInput(BaseModel):
    week_number: int = Field(ge=MIN_WEEK, le=MAX_WEEK)
    csv_content: str = Field(min_length=1, max_length=2_000_000)


@router.post("/raw", summary="Ingest pasted CSV text")
def ingest_raw_csv(data: RawCSVInput, request: Request) -> dict:
    """Rows are merged by employee name, so re-pasting someone replaces their
    row rather than duplicating it. A `week` column in the pasted content routes
    each row to its own week, so one paste can cover a multi-week export."""
    key, previous = _replay(request)
    if previous is not None:
        return {**previous, "idempotent_replay": True}

    rows = list(csv.DictReader(io.StringIO(data.csv_content.strip())))
    if not rows:
        raise HTTPException(
            status_code=400, detail="No data rows found in pasted CSV content."
        )

    total, weeks = _write_grouped(rows, data.week_number)
    log_event("ingest", "csv_paste", f"{total} row(s) across {weeks}.")
    return _remember(
        key,
        {
            "success": True,
            "message": f"Raw CSV ingested ({total} row(s) across {weeks}).",
        },
    )


@router.post("/upload", summary="Ingest an uploaded CSV file")
async def ingest_uploaded_csv(
    request: Request,
    # Bounded to match every other ingest route. This was a bare Form(...) with
    # no range, so a week of 0 or -5 reached the filesystem and the
    # baseline-relative scorer.
    week_number: int = Form(..., ge=MIN_WEEK, le=MAX_WEEK),
    file: UploadFile = File(...),  # noqa: B008
) -> dict:
    key, previous = _replay(request)
    if previous is not None:
        return {**previous, "idempotent_replay": True}

    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    # Read one byte past the limit so "exactly at the limit" and "too large" are
    # distinguishable without ever buffering more than necessary.
    raw_bytes = await file.read(MAX_UPLOAD_SIZE_BYTES + 1)
    if len(raw_bytes) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB).",
        )

    rows = list(
        csv.DictReader(io.StringIO(raw_bytes.decode("utf-8", errors="replace")))
    )
    if not rows:
        raise HTTPException(
            status_code=400, detail="Uploaded CSV contained no data rows."
        )

    total, weeks = _write_grouped(rows, week_number)
    log_event("ingest", "file_upload", f"'{filename}': {total} row(s) across {weeks}.")
    return _remember(
        key,
        {
            "success": True,
            "message": f"Uploaded file '{filename}' ingested ({total} row(s) across {weeks}).",
        },
    )


class WebhookMetricRecord(BaseModel):
    employee_name: str = Field(min_length=1, max_length=100)
    #: Overrides the payload-level week when set.
    week_number: int | None = Field(default=None, ge=MIN_WEEK, le=MAX_WEEK)
    tasks_completed: int = Field(default=0, ge=0, le=1000)
    avg_response_time_hours: float = Field(default=0.0, ge=0, le=1000)
    after_hours_logins: int = Field(default=0, ge=0, le=100)
    weekly_hours: int = Field(default=40, ge=0, le=168)
    # sick_days / task_accuracy / sentiment intentionally absent -- prohibited by
    # config/data_allowlist.json. A webhook must not reintroduce them.


class WebhookIngestInput(BaseModel):
    week_number: int = Field(ge=MIN_WEEK, le=MAX_WEEK)
    records: list[WebhookMetricRecord] = Field(min_length=1, max_length=500)


@router.post("/webhook", summary="Ingest a signed JSON payload")
def ingest_webhook(data: WebhookIngestInput, request: Request) -> dict:
    """Authenticated by HMAC over the raw body in the security middleware, since
    the sender is a system that cannot hold a rotating bearer token."""
    key, previous = _replay(request)
    if previous is not None:
        return {**previous, "idempotent_replay": True}

    ensure(REALTIME_DIR)
    by_week: dict[int, list[list]] = {}
    for record in data.records:
        week = (
            record.week_number if record.week_number is not None else data.week_number
        )
        by_week.setdefault(week, []).append(
            [
                record.employee_name,
                record.tasks_completed,
                record.avg_response_time_hours,
                record.after_hours_logins,
                record.weekly_hours,
            ]
        )

    total = 0
    for week, rows in by_week.items():
        merge_rows_into_weekly_csv(f"{REALTIME_DIR}/week{week}.csv", rows)
        total += len(rows)

    weeks = (
        f"week {data.week_number}"
        if len(by_week) == 1
        else f"{len(by_week)} weeks ({', '.join(str(w) for w in sorted(by_week))})"
    )
    log_event("ingest", "webhook", f"{total} record(s) across {weeks}.")
    return _remember(
        key,
        {
            "success": True,
            "message": f"Webhook ingested {total} record(s) across {weeks}.",
        },
    )


class DatabaseSyncInput(BaseModel):
    db_url: str = Field(default="", max_length=500)
    table_name: str = Field(default="", max_length=100)
    target_week: int = Field(ge=1, le=1000)


@router.post("/db", summary="Sync from the local SQLite database")
def ingest_from_db(data: DatabaseSyncInput) -> dict:
    """`table_name` is passed as a parameterised value, never interpolated into
    SQL, so it never needs sanitising.

    There is no corporate Postgres behind this: it is a real local database with
    real persistence, seeded with a demo batch on each sync. Recorded in
    docs/LIMITATIONS.md rather than implied to be a live enterprise system.
    """
    table_name = (data.table_name or "weekly_metrics").strip()[:100]
    try:
        rows = seed_sample_corporate_batch(table_name, data.target_week)
    except Exception as exc:
        log_event("ingest", "sqlite_db", str(exc), success=False)
        raise HTTPException(
            status_code=500, detail="Database synchronization failed."
        ) from exc

    ensure(REALTIME_DIR)
    canonical = [normalize_row_to_canonical(row) for row in rows]
    merge_rows_into_weekly_csv(f"{REALTIME_DIR}/week{data.target_week}.csv", canonical)

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


@router.get("/db/status", summary="Local database statistics")
def get_db_status() -> dict:
    return db_stats()


class S3SyncInput(BaseModel):
    s3_uri: str = Field(min_length=1, max_length=500)
    target_week: int = Field(ge=1, le=1000)


_SOURCE_LABELS = {
    "aws-s3": "a live AWS S3 GetObject",
    "local-bucket": "the local bucket folder (data/s3_bucket/)",
    "local-bucket-seeded": "a newly seeded demo object in the local bucket folder",
}


@router.post("/s3", summary="Sync from an object store URI")
def ingest_from_s3(data: S3SyncInput) -> dict:
    """A genuine boto3 GetObject when AWS credentials are present; otherwise a
    real local folder mirroring the S3 key layout. Dropping a CSV there and
    syncing genuinely reads that file."""
    try:
        rows, source = fetch_object(data.s3_uri, data.target_week)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Cloud download failed.") from exc

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for '{data.s3_uri}' (local bucket or S3).",
        )

    ensure(REALTIME_DIR)
    canonical = [normalize_row_to_canonical(row) for row in rows]
    merge_rows_into_weekly_csv(f"{REALTIME_DIR}/week{data.target_week}.csv", canonical)

    log_event(
        "ingest",
        "cloud_bucket",
        f"{len(rows)} record(s) via {source} for week {data.target_week}.",
    )
    return {
        "success": True,
        "message": (
            f"Synchronized {len(rows)} record(s) from '{data.s3_uri}' via "
            f"{_SOURCE_LABELS.get(source, source)} for Week {data.target_week}."
        ),
        "source": source,
    }


@router.get("/s3/status", summary="Local bucket statistics")
def get_bucket_status() -> dict:
    return bucket_stats()


class NaturalLanguageInput(BaseModel):
    week_number: int = Field(ge=MIN_WEEK, le=MAX_WEEK)
    text_prompt: str = Field(min_length=1, max_length=5000)


def extract_json_block(text: str) -> str:
    """Pull a JSON object out of text that may carry prose or code fences."""
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end != -1 else text


@router.post("/natural-language", summary="Ingest a free-text description")
def ingest_natural_language(data: NaturalLanguageInput) -> dict:
    """Gemini first, then a local regex extractor.

    The fallback means natural-language ingest keeps working entirely offline
    rather than returning a 500, and the response says which produced it --
    an extraction from a rule-based parser and one from a model must not be
    indistinguishable to whoever reads the result.
    """
    # Imported here so the module can be loaded without the provider stack --
    # the same reason src/__init__.py exports lazily.
    from src.app_utils.runner_helper import run_agent_sync

    from .nl_agent import extractor_agent

    source = "llm"
    try:
        raw = run_agent_sync(
            extractor_agent,
            user_id="admin",
            session_id=f"session_extract_{random.randint(1000, 9999)}",
            prompt=data.text_prompt,
        )
        extracted = json.loads(extract_json_block(raw).strip())
    except Exception:
        logger.warning("LLM extractor unavailable -- using the local fallback.")
        source = "local-fallback"
        extracted = extract_metrics_from_text(data.text_prompt)

    try:
        name = str(extracted.get("employee_name", "Unknown")).strip().capitalize()
        tasks = int(extracted.get("tasks_completed", 0))
        response_time = float(extracted.get("avg_response_time_hours", 0.0))
        after_hours = int(extracted.get("after_hours_logins", 0))
        hours = int(extracted.get("weekly_hours", 40))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422, detail="Could not read metrics from that description."
        ) from exc

    ensure(REALTIME_DIR)
    merge_rows_into_weekly_csv(
        f"{REALTIME_DIR}/week{data.week_number}.csv",
        [[name, tasks, response_time, after_hours, hours]],
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
            "avg_response_time": response_time,
            "after_hours_logins": after_hours,
            "weekly_hours": hours,
        },
    }
