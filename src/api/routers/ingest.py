# src/api/routers/ingest.py
# The CSV-shaped ingest paths: pasted text, uploaded file, signed webhook.
#
# The system-shaped sources (SQLite, object store, natural language) are in
# ingest_sources.py -- same router prefix, split only because one module holding
# all six went past the 400-line limit that tests/unit/test_structure.py
# enforces.
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
import logging

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from src.api.paths import MAX_UPLOAD_SIZE_BYTES, REALTIME_DIR, ensure
from src.api.routers._ingest_shared import (
    idempotency,
)
from src.api.routers._ingest_shared import (
    remember as _remember,
)
from src.api.routers._ingest_shared import (
    replay as _replay,
)
from src.api.routers._ingest_shared import (
    write_grouped as _write_grouped,
)
from src.api.schemas import IngestResult
from src.app_utils.audit_log import log_event
from src.data_layer.ingestion import (
    MAX_WEEK,
    MIN_WEEK,
    merge_rows_into_weekly_csv,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingest"])

__all__ = ["idempotency", "router"]


class RawCSVInput(BaseModel):
    week_number: int = Field(ge=MIN_WEEK, le=MAX_WEEK)
    csv_content: str = Field(min_length=1, max_length=2_000_000)


@router.post("/raw", summary="Ingest pasted CSV text", response_model=IngestResult)
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


@router.post(
    "/upload", summary="Ingest an uploaded CSV file", response_model=IngestResult
)
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


@router.post(
    "/webhook", summary="Ingest a signed JSON payload", response_model=IngestResult
)
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
