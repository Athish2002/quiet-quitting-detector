# src/app_utils/progress.py
# Thread-safe in-memory progress tracker for a pipeline run.
#
# The pipeline (run_orchestrator) can take a while -- each employee/week
# potentially means a real Gemini call (or several, across the fallback
# chain). Running it in a background thread and polling this tracker lets
# the UI show a real, moving progress bar instead of an indefinite spinner.
# Process-local and single-run: fine for this single-user local console --
# not meant to survive a restart or coordinate across multiple workers.

import threading

_lock = threading.Lock()
_state: dict = {
    "running": False,
    "scope": None,
    "done": 0,
    "total": 0,
    "current": "",
    "error": None,
}


def try_start(scope: str) -> bool:
    """Atomically reserve the single pipeline slot. Returns False if a run is
    already active.

    This exists because a check-then-start pattern (`if is_running(): reject`
    followed by `start()` later, once the row count is known) leaves a wide
    TOCTOU window: the caller has to ingest and preprocess CSVs before it can
    compute `total`, and concurrent requests all pass the check during that
    gap -- launching several pipelines that write the same per-employee memory
    files and spend duplicate API quota. Reserving the slot in one locked
    operation closes that window; `set_total()` fills in the count afterwards.
    """
    with _lock:
        if _state["running"]:
            return False
        _state.update(
            running=True, scope=scope, done=0, total=1, current="", error=None
        )
        return True


def set_total(total: int) -> None:
    """Set the expected unit count once it is known (after preprocessing)."""
    with _lock:
        _state["total"] = max(total, 1)


def start(scope: str, total: int) -> None:
    """Unconditionally begin a run. Prefer try_start() + set_total() in request
    handlers, where two callers can race; this remains for direct/scripted use
    (e.g. run_pipeline.py) where single-threaded execution is guaranteed.
    """
    with _lock:
        _state.update(
            running=True,
            scope=scope,
            done=0,
            total=max(total, 1),
            current="",
            error=None,
        )


def update(current: str, done: int | None = None) -> None:
    with _lock:
        _state["current"] = current
        if done is not None:
            _state["done"] = done
        else:
            _state["done"] += 1


def finish(error: str | None = None) -> None:
    with _lock:
        _state["running"] = False
        _state["current"] = ""
        _state["error"] = error


def snapshot() -> dict:
    with _lock:
        return dict(_state)


def is_running() -> bool:
    with _lock:
        return bool(_state["running"])
