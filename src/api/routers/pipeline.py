# src/api/routers/pipeline.py
# Starting a cohort run, and watching it.
#
# Runs happen on a background thread so the request returns immediately and the
# UI polls for a real moving progress bar rather than blocking on an indefinite
# spinner. The slot is reserved ATOMICALLY before the thread starts: a
# check-then-start would let a double-click or two open tabs each launch a run
# against the same memory files, and two orchestrators writing the same
# person's week is corruption nobody would see until the numbers were wrong.

from __future__ import annotations

import logging
import threading

from fastapi import APIRouter, HTTPException

from src.api.paths import (
    MAIN_REPORT,
    MEMORY_DIR,
    REALTIME_DIR,
    REALTIME_MEMORY_DIR,
    REALTIME_REPORT,
    WEEKLY_DIR,
    ensure,
)
from src.app_utils import progress
from src.app_utils.audit_log import log_event
from src.data_layer.ingestion import ingest_weekly_csvs
from src.data_layer.preprocessing import preprocess_employee_records
from src.orchestrator_agent import run_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pipeline"])


def _run_in_background(
    scope: str, weekly_folder: str, memory_folder: str, report_path: str
) -> None:
    def _worker() -> None:
        try:
            try:
                raw_rows = ingest_weekly_csvs(weekly_folder)
                employee_records, max_week = preprocess_employee_records(raw_rows)
                total = max(1, len(employee_records) * max(max_week, 1))
            except Exception:
                logger.warning(
                    "Could not pre-compute the progress total for the %s run; "
                    "falling back to an indeterminate count.",
                    scope,
                    exc_info=True,
                )
                total = 1

            # The slot was reserved by the caller via try_start(); this only
            # fills in the now-known unit count.
            progress.set_total(total)

            report_output = run_orchestrator(
                weekly_folder=weekly_folder,
                memory_folder=memory_folder,
                progress_cb=progress.update,
            )
            with open(report_path, "w", encoding="utf-8") as fh:
                fh.write(report_output)
            log_event("pipeline_run", scope, f"{scope.capitalize()} cohort evaluated.")
            progress.finish()
        except Exception as exc:
            log_event("pipeline_run", scope, str(exc), success=False)
            progress.finish(error=str(exc))

    try:
        threading.Thread(target=_worker, daemon=True).start()
    except Exception as exc:
        # Releasing the reserved slot here is essential: without it a failed
        # thread spawn leaves `running` latched on and every later run 409s
        # until the process restarts.
        progress.finish(error=f"Could not start pipeline thread: {exc}")
        raise


def _start(scope: str, weekly: str, memory: str, report: str, message: str) -> dict:
    if not progress.try_start(scope):
        raise HTTPException(
            status_code=409, detail="A pipeline run is already in progress."
        )
    _run_in_background(scope, weekly, memory, report)
    return {"success": True, "message": message, "started": True}


@router.post("/run", summary="Start the main cohort pipeline")
def execute_pipeline() -> dict:
    """Returns immediately. Poll GET /run/progress, then GET /employees."""
    return _start("main", WEEKLY_DIR, MEMORY_DIR, MAIN_REPORT, "Pipeline started.")


@router.post("/run/realtime", summary="Start the realtime cohort pipeline")
def execute_realtime_pipeline() -> dict:
    # Directories first: idempotent, and doing them before reserving the slot
    # means a filesystem error cannot leave the run flag stuck on.
    ensure(REALTIME_DIR, REALTIME_MEMORY_DIR)
    return _start(
        "realtime",
        REALTIME_DIR,
        REALTIME_MEMORY_DIR,
        REALTIME_REPORT,
        "Real-time pipeline started.",
    )


@router.get("/run/progress", summary="Current run progress")
def get_run_progress() -> dict:
    """{running, scope, done, total, current, error}"""
    return progress.snapshot()
