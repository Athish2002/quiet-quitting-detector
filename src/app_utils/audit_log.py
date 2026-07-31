# src/app_utils/audit_log.py
# Append-only audit log (data/audit_log.jsonl) recording every ingestion
# event and pipeline run, for the History page. One JSON object per line so
# it can be appended to cheaply and tail-read without parsing the whole file
# as a single JSON document.

import json
import os
from datetime import UTC, datetime

AUDIT_LOG_PATH = os.path.join("data", "audit_log.jsonl")
DEFAULT_LIMIT = 200


def log_event(action: str, source: str, detail: str = "", success: bool = True) -> None:
    """Append one event. Never raises -- audit logging must not break callers."""
    event = {
        "timestamp": datetime.now(UTC).isoformat(),
        "action": action,
        "source": source,
        "detail": detail,
        "success": success,
    }
    try:
        os.makedirs(os.path.dirname(AUDIT_LOG_PATH) or ".", exist_ok=True)
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except Exception:
        pass


def read_events(limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Return the most recent events, newest first."""
    if not os.path.exists(AUDIT_LOG_PATH):
        return []
    events: list[dict] = []
    try:
        with open(AUDIT_LOG_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    events.reverse()
    return events[:limit]


def clear_events() -> None:
    try:
        if os.path.exists(AUDIT_LOG_PATH):
            os.remove(AUDIT_LOG_PATH)
    except Exception:
        pass
