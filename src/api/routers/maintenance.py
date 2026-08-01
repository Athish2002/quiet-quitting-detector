# src/api/routers/maintenance.py
# Destructive operations. Admin-only, enforced in src/security/policy.py.
#
# `POST /api/memory/clear` is the route blocker B1 was named for: it wiped every
# stored evaluation with no authentication at all. It still wipes them -- that
# is what it is for -- but now only for an admin key, and the attempt is written
# to the hash-chained audit log with the caller's key ID either way.

from __future__ import annotations

import glob
import logging
import os

from fastapi import APIRouter, HTTPException

from src.api.paths import (
    MAIN_REPORT,
    MEMORY_DIR,
    REALTIME_DIR,
    REALTIME_MEMORY_DIR,
    REALTIME_REPORT,
)
from src.app_utils.audit_log import log_event

logger = logging.getLogger(__name__)

router = APIRouter(tags=["maintenance"])


def _remove_matching(directory: str, pattern: str) -> int:
    if not os.path.exists(directory):
        return 0
    removed = 0
    for path in glob.glob(os.path.join(directory, pattern)):
        try:
            os.remove(path)
            removed += 1
        except OSError:
            logger.warning("Could not remove a file during clear.", exc_info=True)
    return removed


def _remove_file(path: str) -> None:
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            logger.warning("Could not remove %s during clear.", path, exc_info=True)


@router.post("/memory/clear", summary="Delete all main-cohort evaluations")
def clear_pipeline_data() -> dict:
    try:
        removed = _remove_matching(MEMORY_DIR, "*.json")
        _remove_file(MAIN_REPORT)
        log_event("reset", "main", "Main cohort memory and report cleared.")
        return {
            "success": True,
            "message": "All pipeline data and memory cleared.",
            "files_removed": removed,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to clear memory.") from exc


@router.post("/memory/clear/realtime", summary="Delete all realtime-cohort data")
def clear_realtime_data() -> dict:
    try:
        removed = _remove_matching(REALTIME_MEMORY_DIR, "*.json")
        removed += _remove_matching(REALTIME_DIR, "*.csv")
        _remove_file(REALTIME_REPORT)
        log_event("reset", "realtime", "Real-time cohort memory and CSVs cleared.")
        return {
            "success": True,
            "message": "Real-time data and memory cleared.",
            "files_removed": removed,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail="Failed to clear real-time data."
        ) from exc
