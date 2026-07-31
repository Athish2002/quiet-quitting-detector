# src/app_utils/names.py
# Shared helper for safely extracting a first name from free-text employee
# name fields coming from CSV rows, LLM extraction, or API payloads.

FALLBACK_NAME = "Unknown"


def first_name_of(raw_name: str | None, default: str = FALLBACK_NAME) -> str:
    """Return the first whitespace-delimited token of raw_name.

    Falls back to `default` when raw_name is None, empty, or contains only
    whitespace -- avoids the IndexError that `raw_name.split()[0]` raises on
    blank/whitespace-only input (e.g. a CSV cell containing a single space).
    """
    if not raw_name:
        return default
    parts = raw_name.split()
    return parts[0] if parts else default
