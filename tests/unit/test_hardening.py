# Regression tests for the production-hardening pass.
#
# Each test here corresponds to a defect that was reproduced first and fixed
# second, so a regression re-breaks a test rather than silently corrupting data:
#
#   1. Week numbers were unbounded on the upload path and for CSV-embedded week
#      columns, letting week <= 0 reach the filesystem and the baseline-relative
#      scorer (which anchors on week 1, so earlier weeks are scored as if they
#      came after the baseline).
#   2. Pipeline start used check-then-start, so concurrent requests all passed
#      the guard and launched runs against the same memory files.
#   3. The API counter file used a racy read-modify-write and a non-atomic
#      write, losing counts and leaving truncated JSON behind on a crash.

import json
import threading

import pytest

from src.app_utils import progress
from src.data_layer.ingestion import (
    MAX_WEEK,
    MIN_WEEK,
    group_rows_by_week,
    is_valid_week,
)

# ---------------------------------------------------------------------------
# 1. Week-number bounds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("week", [MIN_WEEK, 2, 52, MAX_WEEK])
def test_valid_weeks_accepted(week):
    assert is_valid_week(week)


@pytest.mark.parametrize("week", [0, -1, -5, MAX_WEEK + 1, 999_999_999])
def test_out_of_range_weeks_rejected(week):
    assert not is_valid_week(week)


@pytest.mark.parametrize("hostile", ["-5", "0", "999999999", "not-a-number", ""])
def test_embedded_week_column_cannot_escape_valid_range(hostile):
    """A CSV cell must never place rows outside [MIN_WEEK, MAX_WEEK].

    Previously these produced buckets like -5 / 0 / 999999999, which became
    junk files (week-5.csv) and corrupted baseline-relative scoring.
    """
    grouped = group_rows_by_week(
        [{"employee_name": "A", "week": hostile}], default_week=3
    )
    assert list(grouped) == [3]
    assert all(is_valid_week(w) for w in grouped)


def test_valid_embedded_week_still_honored():
    """The multi-week routing feature must keep working -- in-range values are
    still respected rather than being flattened onto the default."""
    rows = [
        {"employee_name": "A", "week": "1"},
        {"employee_name": "B", "week": "4"},
        {"employee_name": "C"},  # no week -> default
    ]
    grouped = group_rows_by_week(rows, default_week=2)
    assert sorted(grouped) == [1, 2, 4]


def test_mixed_valid_and_hostile_weeks_partition_correctly():
    rows = [
        {"employee_name": "A", "week": "2"},
        {"employee_name": "B", "week": "-7"},
        {"employee_name": "C", "week": "5"},
    ]
    grouped = group_rows_by_week(rows, default_week=1)
    assert sorted(grouped) == [1, 2, 5]  # -7 routed to the validated default


# ---------------------------------------------------------------------------
# 2. Pipeline slot reservation must be atomic
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_progress():
    progress.finish()
    yield
    progress.finish()


def test_try_start_reserves_immediately():
    assert progress.try_start("main") is True
    assert progress.is_running() is True


def test_try_start_rejects_second_caller():
    assert progress.try_start("main") is True
    assert progress.try_start("realtime") is False


def test_only_one_of_many_concurrent_callers_wins():
    """The original check-then-start pattern let all concurrent callers through;
    exactly one may now win."""
    winners = []
    barrier = threading.Barrier(12)

    def contend():
        barrier.wait()  # maximise real overlap
        if progress.try_start("main"):
            winners.append(threading.current_thread().name)

    threads = [threading.Thread(target=contend) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(winners) == 1, f"expected exactly 1 winner, got {len(winners)}"


def test_slot_is_reusable_after_finish():
    assert progress.try_start("main") is True
    progress.finish()
    assert progress.try_start("main") is True


def test_set_total_updates_count_without_restarting():
    progress.try_start("main")
    progress.update("Arjun -- week 1")
    progress.set_total(24)
    snap = progress.snapshot()
    assert snap["total"] == 24
    assert snap["done"] == 1  # progress preserved, not reset
    assert snap["running"] is True


def test_set_total_floors_at_one():
    progress.try_start("main")
    progress.set_total(0)
    assert progress.snapshot()["total"] == 1


# ---------------------------------------------------------------------------
# 3. API metrics: atomic, lock-serialised, corruption-tolerant
# ---------------------------------------------------------------------------


@pytest.fixture
def metrics_path(tmp_path, monkeypatch):
    """Point the metrics writer at a temp file so tests never touch the real one.

    Through the environment, because that is where the path comes from
    (src/config.py). Patching a module constant tested a value the running
    application no longer reads.
    """
    path = tmp_path / "api_metrics.json"
    monkeypatch.setenv("API_METRICS_PATH", str(path))
    return path


def test_metrics_increment_from_absent_file(metrics_path):
    from src.app_utils import runner_helper

    runner_helper._update_metrics(True)
    assert json.loads(metrics_path.read_text()) == {"success": 1, "rejected": 0}


def test_metrics_counts_successes_and_fallbacks_separately(metrics_path):
    from src.app_utils import runner_helper

    for _ in range(3):
        runner_helper._update_metrics(True)
    for _ in range(2):
        runner_helper._update_metrics(False)
    assert json.loads(metrics_path.read_text()) == {"success": 3, "rejected": 2}


def test_no_counts_lost_under_concurrency(metrics_path):
    """The unlocked read-modify-write lost increments when threads interleaved."""
    from src.app_utils import runner_helper

    threads = [
        threading.Thread(target=runner_helper._update_metrics, args=(True,))
        for _ in range(60)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert json.loads(metrics_path.read_text())["success"] == 60


def test_corrupt_metrics_file_is_recovered_not_fatal(metrics_path):
    """A truncated file (killed mid-write by an older build) must not raise."""
    from src.app_utils import runner_helper

    metrics_path.write_text('{"success": 5, "reject')  # truncated JSON
    runner_helper._update_metrics(True)
    assert json.loads(metrics_path.read_text()) == {"success": 1, "rejected": 0}


def test_metrics_leaves_no_temp_files_behind(metrics_path):
    """Atomic replace must clean up after itself."""
    from src.app_utils import runner_helper

    runner_helper._update_metrics(True)
    leftovers = list(metrics_path.parent.glob(".api_metrics_*.tmp"))
    assert leftovers == []


def test_metrics_write_is_never_fatal_to_caller(tmp_path, monkeypatch):
    """Instrumentation must not break the request it measures."""
    from src.app_utils import runner_helper

    # A path under a regular FILE forces the write to fail: os.makedirs cannot
    # create a directory there. (A NUL byte would be rejected by os.environ
    # itself on Windows, before the writer ever saw the value.)
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("", encoding="utf-8")
    monkeypatch.setenv("API_METRICS_PATH", str(blocker / "m.json"))
    runner_helper._update_metrics(True)  # must not raise
