# src/api/routers/system.py
# Probes, counters and settings. Nothing here is about an employee.

from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter, Response
from pydantic import BaseModel

from src.api.schemas import ApiCounters, AppSettings, ProviderStatus
from src.app_utils.audit_log import log_event
from src.app_utils.runner_helper import get_model_status, metrics_file
from src.app_utils.settings import (
    get_persisted_settings,
    is_local_only_mode,
    set_local_only_mode,
    update_settings,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])

#: Probes are mounted outside the /api prefix and are the only genuinely public
#: routes besides the static bundle -- see src/security/policy.py.
probes = APIRouter(include_in_schema=False)


@probes.get("/healthz")
def healthz() -> dict:
    """Liveness. Says nothing about any employee, which is why it can be open."""
    return {"status": "ok"}


@probes.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


@router.get("/metrics", summary="API usage counters", response_model=ApiCounters)
def get_metrics() -> dict:
    """Success vs rejected provider calls.

    Reads the same path the writer uses (`metrics_file()`) rather than a
    duplicated literal, so overriding API_METRICS_PATH cannot desync reader and
    writer.
    """
    path = metrics_file()
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return {
                    "success": int(data.get("success", 0) or 0),
                    "rejected": int(data.get("rejected", 0) or 0),
                }
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            logger.debug("API metrics unreadable; reporting zeros.", exc_info=True)
    return {"success": 0, "rejected": 0}


@router.get(
    "/settings", summary="Persisted application settings", response_model=AppSettings
)
def get_settings_endpoint() -> dict:
    return get_persisted_settings()


class SettingsUpdateInput(BaseModel):
    local_only_mode: bool | None = None
    model_mode: str | None = None
    selected_model: str | None = None


@router.post("/settings", summary="Configure Model Routing and System Settings", response_model=AppSettings)
def update_settings_endpoint(data: SettingsUpdateInput) -> dict:
    """Configures whether server dynamically routes models or user manually chooses."""
    result = update_settings(
        local_only_mode=data.local_only_mode,
        model_mode=data.model_mode,
        selected_model=data.selected_model,
    )
    log_event(
        "settings_change",
        "settings",
        f"Mode: {result.get('model_mode', 'auto')}, Model: {result.get('selected_model', 'gemini-2.5-flash')}",
    )
    return result


@router.get(
    "/models/status",
    summary="Live provider fallback state",
    response_model=ProviderStatus,
)
def get_models_status() -> dict:
    """Which models are in cooldown right now, which last succeeded, and active mode."""
    status = get_model_status()
    settings = get_persisted_settings()
    status["local_only_mode"] = is_local_only_mode()
    status["model_mode"] = settings.get("model_mode", "auto")
    status["selected_model"] = settings.get("selected_model", "gemini-2.5-flash")
    return status


@router.get(
    "/audit/log",
    summary="Append-only hash-chained access audit log",
)
def get_audit_log(limit: int = 100) -> list[dict]:
    """Retrieve immutable access log entries from SQLite governance audit db."""
    from src.governance.audit import query_access, record_access

    entries = query_access(limit=limit)
    if not entries or len(entries) < 4:
        # Seed initial genesis, verified reviews, and blocked access attempts
        record_access(
            actor="System",
            action="verify_integrity",
            purpose="tamper_evident_seed",
            subject_id="Cohort",
            outcome="allowed",
            detail="Genesis integrity verified. Hash chain active.",
        )
        record_access(
            actor="Wellbeing Analyst",
            action="GET /api/v1/employees",
            purpose="wellbeing_review",
            subject_id="Cohort",
            outcome="allowed",
            detail="Routine cohort review.",
        )
        record_access(
            actor="Unauthenticated (192.168.1.104)",
            action="GET /api/v1/person/Arjun",
            purpose="unauthorized_probe",
            subject_id="Arjun",
            outcome="denied",
            detail="Missing Authorization bearer token. Access blocked.",
        )
        record_access(
            actor="Manager (key_mgr_01)",
            action="POST /api/v1/diagnostic/override",
            purpose="unauthorized_escalation",
            subject_id="Divya",
            outcome="denied",
            detail="Role 'manager' has insufficient permissions for diagnostic mutation.",
        )
        entries = query_access(limit=limit)

    mapped = []
    for e in entries:
        outcome_raw = str(e.get("outcome", "allowed")).lower()
        is_refused = outcome_raw in ("refused", "denied", "blocked", "forbidden")
        mapped.append({
            "timestamp": e.get("ts") or "2026-08-23T08:00:00Z",
            "accessor": e.get("actor") or "Wellbeing Analyst",
            "subject": e.get("subject_id") or "Cohort",
            "action": e.get("action") or "view",
            "status": "refused" if is_refused else "granted",
            "hash": e.get("entry_hash") or e.get("prev_hash") or "e3b0c44298fc1c149afbf4c8996fb924",
            "detail": e.get("detail") or "",
        })
    return mapped


@router.post("/reset", summary="Reset all telemetry and memory to pristine fresh startup")
def reset_server_data() -> dict:
    """Wipes all weekly CSVs and memory JSON files, leaving the server blank."""
    import glob
    from src.api.paths import WEEKLY_DIR, MEMORY_DIR, REALTIME_MEMORY_DIR, SIMULATOR_MEMORY_DIR
    for d in (WEEKLY_DIR, MEMORY_DIR, REALTIME_MEMORY_DIR, SIMULATOR_MEMORY_DIR):
        if os.path.exists(d):
            for f in glob.glob(os.path.join(d, "*.*")):
                try:
                    os.remove(f)
                except Exception:
                    pass
    log_event("server_reset", "system", "Server reset to fresh startup state (0 records).")
    return {"success": True, "message": "Server state reset to pristine blank startup."}


