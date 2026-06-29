"""
Unit tests for STRIDE security fixes.

Tests cover:
  - Fix 1: Session IDs are anonymised (hashed) and never contain first names.
  - Fix 2: _load_employee_history() respects the MAX_HISTORY_WEEKS lookback
            and enforces field integrity.
  - Fix 3: Recurrence bonus decays after HEALTHY_DECAY_WEEKS consecutive
            Healthy weeks.
  - Fix 4: _validate_briefing() blocks unsafe phrases and raw error markers.
"""

import hashlib
import json
import os
import time

import pytest


# ---------------------------------------------------------------------------
# Fix 1 – Anonymised session IDs
# ---------------------------------------------------------------------------


def test_anon_session_id_does_not_contain_first_name():
    """Session ID must never embed the employee first name."""
    from src.risk_scorer_agent import _anon_session_id

    session_id = _anon_session_id("alice", "risk")
    assert "alice" not in session_id, "First name must not appear in session ID"
    assert session_id.startswith("session_employee_"), "Session ID must use safe prefix"


def test_anon_session_id_is_deterministic():
    """Same name + suffix must always produce the same session ID."""
    from src.risk_scorer_agent import _anon_session_id

    assert _anon_session_id("alice", "risk") == _anon_session_id("alice", "risk")


def test_anon_session_id_differs_by_name():
    """Different names must produce different session IDs."""
    from src.risk_scorer_agent import _anon_session_id

    assert _anon_session_id("alice", "risk") != _anon_session_id("bob", "risk")


def test_anon_session_id_differs_by_suffix():
    """Same name but different suffix must produce different session IDs."""
    from src.risk_scorer_agent import _anon_session_id

    assert _anon_session_id("alice", "risk") != _anon_session_id("alice", "briefing")


def test_anon_session_id_hash_matches_sha256():
    """Verify the embedded hash is the first 12 chars of SHA-256."""
    from src.risk_scorer_agent import _anon_session_id

    expected_hash = hashlib.sha256(b"alice").hexdigest()[:12]
    session_id = _anon_session_id("alice", "risk")
    assert expected_hash in session_id


def test_manager_briefing_session_id_anon():
    """Manager briefing agent must also use a hashed session ID."""
    from src.manager_briefing_agent import _anon_session_id as briefing_anon

    session_id = briefing_anon("alice", "briefing")
    assert "alice" not in session_id
    assert session_id.startswith("session_employee_")


def test_manager_briefing_fallback_no_first_name():
    """The safe fallback string in manager_briefing_agent must not contain first names."""
    from src.manager_briefing_agent import _SAFE_FALLBACK_BRIEFING

    # The fallback should be generic — no placeholder for a name.
    # We just confirm no obvious name token appears.
    for name in ("alice", "bob", "{first_name}", "first_name"):
        assert name not in _SAFE_FALLBACK_BRIEFING.lower(), (
            f"Fallback briefing must not contain '{name}'"
        )


# ---------------------------------------------------------------------------
# Fix 2 – Memory lookback cap + integrity check
# ---------------------------------------------------------------------------


def test_load_history_respects_lookback_window(tmp_path, monkeypatch):
    """Files older than MAX_HISTORY_WEEKS must be ignored."""
    import src.risk_scorer_agent as rsa

    monkeypatch.setattr(rsa, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(rsa, "MAX_HISTORY_SECONDS", 7 * 24 * 3600)  # 1 week for test

    # Write a "recent" file (mtime = now)
    recent_file = tmp_path / "alice_week10.json"
    recent_file.write_text(
        json.dumps({"score": 3, "classification": "Healthy", "rationale": "ok", "healthy_streak": 1})
    )

    # Write an "old" file (mtime = 2 weeks ago)
    old_file = tmp_path / "alice_week1.json"
    old_file.write_text(
        json.dumps({"score": 7, "classification": "At Risk", "rationale": "old", "healthy_streak": 0})
    )
    old_mtime = time.time() - (14 * 24 * 3600)  # 14 days ago
    os.utime(str(old_file), (old_mtime, old_mtime))

    history = rsa._load_employee_history("alice")

    # Only the recent file should be loaded.
    assert len(history) == 1, f"Expected 1 record, got {len(history)}"
    assert history[0]["score"] == 3


def test_load_history_skips_records_missing_required_fields(tmp_path, monkeypatch):
    """Records missing required fields must be skipped with a warning, not crash."""
    import src.risk_scorer_agent as rsa

    monkeypatch.setattr(rsa, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(rsa, "MAX_HISTORY_SECONDS", 7 * 24 * 3600)

    # Write a file missing the 'rationale' field
    bad_file = tmp_path / "alice_week5.json"
    bad_file.write_text(json.dumps({"score": 6, "classification": "At Risk"}))

    # Write a valid file
    good_file = tmp_path / "alice_week6.json"
    good_file.write_text(
        json.dumps({"score": 4, "classification": "Watch", "rationale": "mild signals", "healthy_streak": 0})
    )

    history = rsa._load_employee_history("alice")

    assert len(history) == 1, "Corrupt record should be skipped"
    assert history[0]["score"] == 4


def test_load_history_skips_unreadable_json(tmp_path, monkeypatch):
    """Corrupted (unparseable) JSON files must be silently skipped."""
    import src.risk_scorer_agent as rsa

    monkeypatch.setattr(rsa, "MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(rsa, "MAX_HISTORY_SECONDS", 7 * 24 * 3600)

    broken_file = tmp_path / "alice_week3.json"
    broken_file.write_text("NOT VALID JSON {{{{")

    history = rsa._load_employee_history("alice")
    assert history == [], "Unreadable file should produce empty history"


# ---------------------------------------------------------------------------
# Fix 3 – Recurrence bonus decay
# ---------------------------------------------------------------------------


def test_recurrence_bonus_applies_when_elevated_twice(tmp_path, monkeypatch):
    """Bonus must apply when >= 2 of the recent history weeks are Watch-or-above."""
    import src.risk_scorer_agent as rsa

    history = [
        {"score": 6, "classification": "At Risk", "rationale": "r", "healthy_streak": 0},
        {"score": 7, "classification": "At Risk", "rationale": "r", "healthy_streak": 0},
    ]
    apply_bonus, streak = rsa._compute_recurrence_bonus(history)
    assert apply_bonus is True
    assert streak == 0


def test_recurrence_bonus_suppressed_after_decay(tmp_path, monkeypatch):
    """Bonus must NOT apply when employee has >= HEALTHY_DECAY_WEEKS consecutive Healthy weeks."""
    import src.risk_scorer_agent as rsa

    # Simulate 4 consecutive Healthy weeks at the end of history.
    history = [
        {"score": 6, "classification": "At Risk", "rationale": "r", "healthy_streak": 0},
        {"score": 7, "classification": "At Risk", "rationale": "r", "healthy_streak": 0},
        {"score": 2, "classification": "Healthy", "rationale": "r", "healthy_streak": 1},
        {"score": 2, "classification": "Healthy", "rationale": "r", "healthy_streak": 2},
        {"score": 2, "classification": "Healthy", "rationale": "r", "healthy_streak": 3},
        {"score": 2, "classification": "Healthy", "rationale": "r", "healthy_streak": 4},
    ]
    apply_bonus, streak = rsa._compute_recurrence_bonus(history)
    assert apply_bonus is False, "Bonus should be cleared after 4 Healthy weeks"
    assert streak >= rsa.HEALTHY_DECAY_WEEKS


def test_recurrence_bonus_not_applied_on_single_elevated_week():
    """Bonus requires >= 2 elevated weeks; a single elevated week is not enough."""
    import src.risk_scorer_agent as rsa

    history = [
        {"score": 6, "classification": "At Risk", "rationale": "r", "healthy_streak": 0},
    ]
    apply_bonus, _ = rsa._compute_recurrence_bonus(history)
    assert apply_bonus is False


def test_recurrence_bonus_no_history():
    """With no history, no bonus should be applied."""
    import src.risk_scorer_agent as rsa

    apply_bonus, streak = rsa._compute_recurrence_bonus([])
    assert apply_bonus is False
    assert streak == 0


def test_healthy_streak_resets_on_elevated_week():
    """A non-Healthy week at the end of history resets the current streak to 0."""
    import src.risk_scorer_agent as rsa

    history = [
        {"score": 2, "classification": "Healthy", "rationale": "r", "healthy_streak": 3},
        {"score": 6, "classification": "At Risk", "rationale": "r", "healthy_streak": 0},
    ]
    _, streak = rsa._compute_recurrence_bonus(history)
    assert streak == 0, "Streak should reset when most recent week is elevated"


# ---------------------------------------------------------------------------
# Fix 4 – Output validator
# ---------------------------------------------------------------------------


def test_validator_blocks_performance_improvement_plan():
    from src.manager_briefing_agent import _validate_briefing, _SAFE_FALLBACK_BRIEFING

    unsafe = "You should consider a Performance Improvement Plan for this person."
    result = _validate_briefing(unsafe)
    assert result == _SAFE_FALLBACK_BRIEFING


def test_validator_blocks_disciplinary():
    from src.manager_briefing_agent import _validate_briefing, _SAFE_FALLBACK_BRIEFING

    unsafe = "A disciplinary meeting should be scheduled immediately."
    result = _validate_briefing(unsafe)
    assert result == _SAFE_FALLBACK_BRIEFING


def test_validator_blocks_raw_error_prefix():
    from src.manager_briefing_agent import _validate_briefing, _SAFE_FALLBACK_BRIEFING

    unsafe = "Error: API quota exceeded.\nPlease try again later."
    result = _validate_briefing(unsafe)
    assert result == _SAFE_FALLBACK_BRIEFING


def test_validator_blocks_exception_prefix():
    from src.manager_briefing_agent import _validate_briefing, _SAFE_FALLBACK_BRIEFING

    unsafe = "Exception: Connection timeout after 30s."
    result = _validate_briefing(unsafe)
    assert result == _SAFE_FALLBACK_BRIEFING


def test_validator_blocks_termination():
    from src.manager_briefing_agent import _validate_briefing, _SAFE_FALLBACK_BRIEFING

    unsafe = "You may need to consider termination of employment."
    result = _validate_briefing(unsafe)
    assert result == _SAFE_FALLBACK_BRIEFING


def test_validator_blocks_surveillance():
    from src.manager_briefing_agent import _validate_briefing, _SAFE_FALLBACK_BRIEFING

    unsafe = "Consider enabling surveillance on the employee's workstation."
    result = _validate_briefing(unsafe)
    assert result == _SAFE_FALLBACK_BRIEFING


def test_validator_passes_safe_content():
    from src.manager_briefing_agent import _validate_briefing

    safe = (
        "Signals Detected: Declining task completion over 3 weeks.\n"
        "Pre-Meeting Observation: Notice energy levels and tone in team meetings.\n"
        "3 Supportive Things to Say:\n"
        "  1. 'How are you finding your current workload?'\n"
        "  2. 'Is there anything I can do to better support you?'\n"
        "  3. 'I have noticed a change - is everything okay?'\n"
        "2 Things Never to Say:\n"
        "  1. 'Your numbers have dropped.'\n"
        "  2. 'You need to be more engaged or things will change.'"
    )
    result = _validate_briefing(safe)
    assert result == safe, "Safe content should pass through unchanged"


def test_validator_is_case_insensitive():
    from src.manager_briefing_agent import _validate_briefing, _SAFE_FALLBACK_BRIEFING

    # Mixed case — should still be caught
    unsafe = "DISCIPLINARY action is recommended."
    result = _validate_briefing(unsafe)
    assert result == _SAFE_FALLBACK_BRIEFING


def test_validator_safe_fallback_itself_passes():
    """The safe fallback string must itself pass the validator (no circular replacement)."""
    from src.manager_briefing_agent import _validate_briefing, _SAFE_FALLBACK_BRIEFING

    result = _validate_briefing(_SAFE_FALLBACK_BRIEFING)
    assert result == _SAFE_FALLBACK_BRIEFING
