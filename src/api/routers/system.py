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
from src.app_utils.runner_helper import METRICS_FILE, get_model_status
from src.app_utils.settings import get_settings, is_local_only_mode, set_local_only_mode

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

    Reads the same path the writer uses (METRICS_FILE) rather than a duplicated
    literal, so overriding API_METRICS_PATH cannot desync reader and writer.
    """
    if os.path.exists(METRICS_FILE):
        try:
            with open(METRICS_FILE, encoding="utf-8") as fh:
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
    return get_settings()


class SettingsUpdateInput(BaseModel):
    local_only_mode: bool


@router.post("/settings", summary="Toggle Local-Only Mode", response_model=AppSettings)
def update_settings_endpoint(data: SettingsUpdateInput) -> dict:
    """Local-Only Mode skips every Gemini call and goes straight to the local
    fallback tiers, so quota can be deliberately stopped once rate-limited."""
    result = set_local_only_mode(data.local_only_mode)
    log_event(
        "settings_change",
        "settings",
        f"Local-Only Mode {'enabled' if data.local_only_mode else 'disabled'}",
    )
    return result


@router.get(
    "/models/status",
    summary="Live provider fallback state",
    response_model=ProviderStatus,
)
def get_models_status() -> dict:
    """Which models are in cooldown right now, which last succeeded, and whether
    Local-Only Mode is skipping all of them by choice.

    Real current state rather than a cumulative counter: the UI previously had
    to guess exhaustion from a running total, which is wrong the moment a
    cooldown expires.
    """
    status = get_model_status()
    status["local_only_mode"] = is_local_only_mode()
    return status
