# src/api/routers/_ingest_shared.py
# Helpers every ingest path uses.
#
# Extracted so `ingest.py` (the CSV-shaped sources) and `ingest_sources.py`
# (the system-shaped ones) share ONE idempotency store and ONE writer. Two
# copies of either would be two places for a retry to slip through, and the
# whole point of routing every source through `merge_rows_into_weekly_csv` is
# that no source can become a way around the governance layer.

from __future__ import annotations

from fastapi import Request

from src.api.paths import REALTIME_DIR, ensure
from src.data_layer.ingestion import (
    group_rows_by_week,
    merge_rows_into_weekly_csv,
    normalize_row_to_canonical,
)
from src.security import IdempotencyStore

#: One store, shared by every ingest route. A sender that times out and retries
#: -- which is what every sender eventually does -- would otherwise append a
#: second copy of the week. Nobody sees an error: one person's metrics silently
#: double, which reads as an employee whose output suddenly improved.
idempotency = IdempotencyStore()


def replay(request: Request) -> tuple[str | None, dict | None]:
    """The Idempotency-Key and any response already stored against it."""
    key = request.headers.get("Idempotency-Key")
    return key, idempotency.seen(key) if key else None


def remember(key: str | None, result: dict) -> dict:
    if key:
        idempotency.remember(key, result)
    return result


def write_grouped(raw_rows: list[dict], default_week: int) -> tuple[int, str]:
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
