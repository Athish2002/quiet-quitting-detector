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
DEFAULT_SETTINGS = {"local_only_mode": False}


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
    """The stored preferences.

    Named apart from `src.config.get_settings` on purpose: that one is the
    validated ENVIRONMENT, this one is the single toggle a user flips at
    runtime. Two functions called `get_settings` in one codebase is a bug
    waiting for whoever imports the wrong one.
    """
    return _load()


def is_local_only_mode() -> bool:
    return bool(_load().get("local_only_mode", False))


def set_local_only_mode(enabled: bool) -> dict:
    settings = _load()
    settings["local_only_mode"] = bool(enabled)
    os.makedirs(os.path.dirname(SETTINGS_PATH) or ".", exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    return settings
