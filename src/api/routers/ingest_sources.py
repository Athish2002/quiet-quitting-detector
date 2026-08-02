# src/api/routers/ingest_sources.py
# The system-shaped ingest paths: SQLite, object store, natural language.
#
# Split out of ingest.py purely on size -- same router prefix, same shared
# helpers, same guarantee that every source converges on
# `merge_rows_into_weekly_csv` after `normalize_row_to_canonical` so none of
# them becomes a route around the governance layer.

from __future__ import annotations

import json
import logging
import random

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.api.paths import REALTIME_DIR, ensure
from src.api.routers._ingest_shared import (
    remember as _remember,
)
from src.api.routers._ingest_shared import (
    replay as _replay,
)
from src.app_utils.audit_log import log_event
from src.app_utils.local_nl_extract import extract_metrics_from_text
from src.data_layer.ingestion import (
    MAX_WEEK,
    MIN_WEEK,
    merge_rows_into_weekly_csv,
    normalize_row_to_canonical,
)
from src.data_layer.s3_store import bucket_stats, fetch_object
from src.data_layer.sql_store import db_stats, seed_sample_corporate_batch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingest"])


class DatabaseSyncInput(BaseModel):
    db_url: str = Field(default="", max_length=500)
    table_name: str = Field(default="", max_length=100)
    target_week: int = Field(ge=1, le=1000)


@router.post("/db", summary="Sync from the local SQLite database")
def ingest_from_db(data: DatabaseSyncInput, request: Request) -> dict:
    """`table_name` is passed as a parameterised value, never interpolated into
    SQL, so it never needs sanitising.

    There is no corporate Postgres behind this: it is a real local database with
    real persistence, seeded with a demo batch on each sync. Recorded in
    docs/LIMITATIONS.md rather than implied to be a live enterprise system.
    """
    key, previous = _replay(request)
    if previous is not None:
        return {**previous, "idempotent_replay": True}

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
    return _remember(
        key,
        {
            "success": True,
            "message": (
                f"Synchronized {len(rows)} employee record(s) from local SQLite "
                f"table '{table_name}' for Week {data.target_week}."
            ),
            "source": "sqlite",
            "db_stats": db_stats(),
        },
    )


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
def ingest_from_s3(data: S3SyncInput, request: Request) -> dict:
    """A genuine boto3 GetObject when AWS credentials are present; otherwise a
    real local folder mirroring the S3 key layout. Dropping a CSV there and
    syncing genuinely reads that file."""
    key, previous = _replay(request)
    if previous is not None:
        return {**previous, "idempotent_replay": True}

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
    return _remember(
        key,
        {
            "success": True,
            "message": (
                f"Synchronized {len(rows)} record(s) from '{data.s3_uri}' via "
                f"{_SOURCE_LABELS.get(source, source)} for Week {data.target_week}."
            ),
            "source": source,
        },
    )


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
def ingest_natural_language(data: NaturalLanguageInput, request: Request) -> dict:
    """Gemini first, then a local regex extractor.

    The fallback means natural-language ingest keeps working entirely offline
    rather than returning a 500, and the response says which produced it --
    an extraction from a rule-based parser and one from a model must not be
    indistinguishable to whoever reads the result.
    """
    key, previous = _replay(request)
    if previous is not None:
        return {**previous, "idempotent_replay": True}

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
    return _remember(
        key,
        {
            "success": True,
            "source": source,
            "extracted": {
                "name": name,
                "tasks_completed": tasks,
                "avg_response_time": response_time,
                "after_hours_logins": after_hours,
                "weekly_hours": hours,
            },
        },
    )
