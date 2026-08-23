# src/app_utils/settings.py
# Small persisted, file-based settings store (data/settings.json).
#
# Currently holds a single toggle -- Local-Only Mode -- that lets the user
# deliberately skip Gemini entirely and go straight to the local fallback
# tiers (trained regression model -> nearest-neighbor match -> hardcoded
# default). Useful once a user knows they're rate-limited: it avoids
# spending a network round trip (and quota) on a call that's likely to
# fail anyway.

import json
import os

SETTINGS_PATH = os.path.join("data", "settings.json")
DEFAULT_SETTINGS = {
    "local_only_mode": False,
    "model_mode": "auto",  # "auto" (server decides) | "manual" (choose model)
    "selected_model": "gemini-2.5-flash",
}


def _load() -> dict:
    if not os.path.exists(SETTINGS_PATH):
        return dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return {**DEFAULT_SETTINGS, **data}
    except Exception:
        return dict(DEFAULT_SETTINGS)


def get_persisted_settings() -> dict:
    return _load()


def is_local_only_mode() -> bool:
    s = _load()
    if s.get("model_mode") == "manual" and s.get("selected_model") == "local-deterministic":
        return True
    return bool(s.get("local_only_mode", False))


def set_local_only_mode(enabled: bool) -> dict:
    settings = _load()
    settings["local_only_mode"] = bool(enabled)
    if enabled:
        settings["model_mode"] = "manual"
        settings["selected_model"] = "local-deterministic"
    elif settings.get("selected_model") == "local-deterministic":
        settings["model_mode"] = "auto"
        settings["selected_model"] = "gemini-2.5-flash"
    os.makedirs(os.path.dirname(SETTINGS_PATH) or ".", exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    return settings


def update_settings(
    local_only_mode: bool | None = None,
    model_mode: str | None = None,
    selected_model: str | None = None,
) -> dict:
    settings = _load()
    if local_only_mode is not None:
        settings["local_only_mode"] = bool(local_only_mode)
    if model_mode is not None:
        settings["model_mode"] = str(model_mode)
        if model_mode == "auto":
            settings["local_only_mode"] = False
    if selected_model is not None:
        settings["selected_model"] = str(selected_model)
        if selected_model == "local-deterministic":
            settings["local_only_mode"] = True
            settings["model_mode"] = "manual"
        elif model_mode == "manual":
            settings["local_only_mode"] = False
    os.makedirs(os.path.dirname(SETTINGS_PATH) or ".", exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    return settings
