# src/api/routers/reports.py
# Generated reports and the system event log.

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from src.api.paths import MAIN_REPORT, REALTIME_REPORT, THREAT_MODEL
from src.api.schemas import Ack, EventLogEntry
from src.app_utils.audit_log import clear_events, read_events

router = APIRouter(tags=["reports"])

#: The three report routes stream a file rather than JSON, so they carry a
#: media type instead of a response model. Declared explicitly because the
#: generated client would otherwise describe a text download as an empty JSON
#: body -- the one place in this API where the schema is not the whole contract.
_TEXT = {200: {"content": {"text/plain": {}}, "description": "The report file."}}
_MARKDOWN = {200: {"content": {"text/markdown": {}}, "description": "The document."}}


def _serve(path: str, media_type: str, missing: str) -> FileResponse:
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=missing)
    return FileResponse(path, media_type=media_type)


@router.get(
    "/history",
    summary="Ingestion and pipeline event log",
    response_model=list[EventLogEntry],
)
def get_history(limit: int = 200) -> list[dict]:
    """Newest first. This is the operational event log, not the access audit
    trail -- that is `src/governance/audit.py` and is hash-chained."""
    return read_events(limit=limit)


@router.post("/history/clear", summary="Clear the event log", response_model=Ack)
def clear_history() -> dict:
    """Clears the operational log only.

    Deliberately cannot touch the governance audit trail, which is append-only
    at the database level. A "clear history" button that erased the record of
    who looked at whom would defeat the point of having one.
    """
    clear_events()
    return {"success": True, "message": "History log cleared."}


@router.get("/report/raw", summary="Main cohort report", responses=_TEXT)
def get_raw_report() -> FileResponse:
    return _serve(MAIN_REPORT, "text/plain", "Engagement report file not found.")


@router.get("/report/realtime", summary="Realtime cohort report", responses=_TEXT)
def get_realtime_report() -> FileResponse:
    return _serve(
        REALTIME_REPORT, "text/plain", "Real-time engagement report file not found."
    )


@router.get("/report/threat-model", summary="STRIDE threat model", responses=_MARKDOWN)
def get_threat_model() -> FileResponse:
    return _serve(THREAT_MODEL, "text/markdown", "Threat model file not found.")
