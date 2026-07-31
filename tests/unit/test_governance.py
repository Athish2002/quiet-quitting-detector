# Phase 0 guardrail tests.
#
# These assert the guardrails are load-bearing rather than documentation:
# prohibited fields cannot reach storage through ANY ingest path, punitive
# purposes are refused by the code, deletion actually deletes, and the
# employee-facing notice cannot drift from the config it describes.

import json

import pytest

from src.governance import allowlist, notice, purpose, retention

# ---------------------------------------------------------------------------
# Data minimization -- default-deny
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "forbidden",
    [
        "sick_days",
        "sick days",
        "Sick-Days",
        "sickDays",  # health
        "medical_notes",
        "leave_reason",
        "fmla_status",
        "disability_status",
        "message_content",
        "chat_text",
        "email_body",
        "sentiment",
        "tone",
        "emotion_score",
        "morale",  # content/emotion
        "keystroke_count",
        "mouse_movements",
        "screenshot_url",
        "webcam_frames",
        "location",
        "gps_coords",
        "ip_address",  # location
        "race",
        "gender",
        "age_band",
        "religion",  # protected
        "union_membership",
        "political_affiliation",
        "salary",
        "bonus_amount",
    ],
)
def test_forbidden_fields_never_survive_ingest(forbidden):
    result = allowlist.filter_record(
        {"employee_name": "A", forbidden: "x"}, source="test", strict=False
    )
    assert forbidden not in result.accepted
    assert result.had_violation, f"{forbidden!r} should be flagged as a violation"


def test_forbidden_field_raises_in_strict_mode():
    with pytest.raises(allowlist.ForbiddenFieldError):
        allowlist.filter_record({"sick_days": "3"}, source="test", strict=True)


def test_forbidden_error_is_not_a_valueerror():
    """Must not be swallowable by the generic `except ValueError` used for parsing."""
    assert not issubclass(allowlist.ForbiddenFieldError, ValueError)


def test_unknown_fields_dropped_quietly_without_violation():
    result = allowlist.filter_record(
        {"employee_name": "A", "some_new_column": "1"}, source="test", strict=True
    )
    assert "some_new_column" in result.dropped_unknown
    assert not result.had_violation  # unknown != prohibited


def test_permitted_fields_pass_through():
    record = {"employee_name": "A", "tasks_completed": "7", "weekly_hours": "40"}
    result = allowlist.filter_record(record, source="test", strict=True)
    assert set(result.accepted) == set(record)


def test_default_deny_is_the_actual_default():
    """A field absent from the allowlist must not be accepted merely because it
    also fails to match a forbidden pattern."""
    result = allowlist.filter_record(
        {"totally_novel_metric": "1"}, source="t", strict=True
    )
    assert result.accepted == {}


def test_wellbeing_only_field_cannot_enter_risk_scoring():
    """after_hours_logins may prompt a check-in but must never raise risk."""
    assert "after_hours_logins" in allowlist.wellbeing_only_fields()
    assert "after_hours_logins" not in allowlist.risk_scoring_fields()


def test_removed_fields_absent_from_canonical_schema():
    """Regression guard: the prohibited columns must not return to the schema."""
    from src.data_layer.ingestion import CANONICAL_HEADER, COLUMN_ALIASES

    for banned in ("sick_days", "task_accuracy", "sentiment"):
        assert banned not in CANONICAL_HEADER
        assert banned not in COLUMN_ALIASES


def test_ingest_path_drops_prohibited_columns_end_to_end():
    """The real normalizer every connector uses must not emit prohibited data."""
    from src.data_layer.ingestion import CANONICAL_HEADER, normalize_row_to_canonical

    row = {
        "employee_name": "Ada",
        "tasks_completed": "5",
        "sick_days": "4",
        "sentiment": "Withdrawn",
        "task_accuracy": "62",
    }
    out = normalize_row_to_canonical(row, source="test")
    assert len(out) == len(CANONICAL_HEADER)
    assert "4" not in out and "Withdrawn" not in out and "62" not in out


# ---------------------------------------------------------------------------
# Purpose binding -- punitive use refused structurally
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_audit(tmp_path, monkeypatch):
    from src.governance import audit

    monkeypatch.setattr(audit, "AUDIT_DB_PATH", str(tmp_path / "audit.db"))
    audit._initialised.clear()
    yield


@pytest.mark.parametrize(
    "banned",
    [
        "termination",
        "pip",
        "performance_improvement_plan",
        "compensation_review",
        "ranking",
        "stack_ranking",
        "disciplinary",
        "employee_facing_score_display",
    ],
)
def test_forbidden_purposes_are_refused(banned):
    with pytest.raises(purpose.PurposeViolation):
        purpose.authorize("ui:manager-console", banned, subject_id="sub_1", reason="r")


def test_unregistered_consumer_refused():
    with pytest.raises(purpose.PurposeDenied):
        purpose.authorize("attacker", "manager_support_conversation", reason="r")


def test_consumer_cannot_use_purpose_it_is_not_registered_for():
    with pytest.raises(purpose.PurposeDenied):
        purpose.authorize(
            "ui:org-health",
            "manager_support_conversation",
            subject_id="sub_1",
            reason="r",
        )


def test_individual_read_requires_reason_for_access():
    with pytest.raises(purpose.PurposeDenied):
        purpose.authorize(
            "ui:manager-console",
            "manager_support_conversation",
            subject_id="sub_1",
            reason="  ",
        )


def test_valid_individual_read_allowed_and_audited():
    from src.governance.audit import query_access

    use = purpose.authorize(
        "ui:manager-console",
        "manager_support_conversation",
        subject_id="sub_1",
        reason="prep for 1:1",
    )
    assert use is purpose.PermittedUse.MANAGER_SUPPORT_CONVERSATION
    entries = query_access(subject_id="sub_1")
    assert entries and entries[0]["outcome"] == "allowed"
    assert entries[0]["detail"] == "prep for 1:1"


def test_refusals_are_audited_not_silent():
    from src.governance.audit import query_access

    with pytest.raises(purpose.PurposeViolation):
        purpose.authorize(
            "ui:manager-console", "termination", subject_id="sub_9", reason="x"
        )
    entries = query_access(subject_id="sub_9")
    assert entries[0]["outcome"] == "policy_violation"


def test_aggregate_read_needs_no_individual_reason():
    assert purpose.authorize("ui:org-health", "aggregate_org_health") is (
        purpose.PermittedUse.AGGREGATE_ORG_HEALTH
    )


# ---------------------------------------------------------------------------
# Audit log -- append-only, and answers a subject access request
# ---------------------------------------------------------------------------


def test_audit_log_rejects_update_and_delete():
    """Immutability enforced by the engine, not by convention."""
    import sqlite3

    from src.governance.audit import AUDIT_DB_PATH, record_access

    record_access(
        actor="a", action="read_score", purpose="model_evaluation", subject_id="sub_x"
    )
    conn = sqlite3.connect(AUDIT_DB_PATH)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE access_log SET actor='forged'")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM access_log")
    finally:
        conn.close()


def test_audit_write_never_raises_even_when_broken(monkeypatch):
    from src.governance import audit

    monkeypatch.setattr(audit, "AUDIT_DB_PATH", "/\0invalid/audit.db")
    audit._initialised.clear()
    audit.record_access(
        actor="a", action="x", purpose="model_evaluation"
    )  # must not raise


def test_subject_access_export_contains_only_that_subject():
    from src.governance.audit import export_subject_access_request, record_access

    record_access(
        actor="m1",
        action="read_score",
        purpose="manager_support_conversation",
        subject_id="sub_a",
    )
    record_access(
        actor="m2",
        action="read_score",
        purpose="manager_support_conversation",
        subject_id="sub_b",
    )
    export = export_subject_access_request("sub_a")
    assert export["access_event_count"] == 1
    assert {e["subject_id"] for e in export["events"]} == {"sub_a"}


# ---------------------------------------------------------------------------
# Retention -- deletion is REAL, and verified
# ---------------------------------------------------------------------------


def _write_score(path, ts):
    path.write_text(json.dumps({"score": 5, "timestamp": ts}), encoding="utf-8")


def test_expired_records_are_really_deleted_not_tombstoned(tmp_path):
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    old = tmp_path / "sub_1_week1.json"
    fresh = tmp_path / "sub_1_week2.json"
    _write_score(old, (now - timedelta(days=500)).isoformat())
    _write_score(fresh, (now - timedelta(days=5)).isoformat())

    report = retention.purge_expired_files(str(tmp_path), "scores", now=now)

    assert report.deleted_count == 1
    assert not old.exists(), "expired record must be gone from disk"
    assert fresh.exists(), "in-policy record must survive"


def test_dry_run_reports_without_deleting(tmp_path):
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    old = tmp_path / "sub_1_week1.json"
    _write_score(old, (now - timedelta(days=500)).isoformat())

    report = retention.purge_expired_files(
        str(tmp_path), "scores", now=now, dry_run=True
    )
    assert report.deleted_count == 1
    assert old.exists()


def test_embedded_timestamp_beats_mtime(tmp_path):
    """Copying/restoring a file refreshes mtime; retention must not be extended
    by that, so the record's own timestamp wins."""
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    f = tmp_path / "sub_1_week1.json"
    _write_score(f, (now - timedelta(days=500)).isoformat())  # old content, new mtime

    report = retention.purge_expired_files(str(tmp_path), "scores", now=now)
    assert report.deleted_count == 1


def test_subject_erasure_removes_only_that_subject(tmp_path):
    from datetime import UTC, datetime

    ts = datetime.now(UTC).isoformat()
    _write_score(tmp_path / "sub_target_week1.json", ts)
    _write_score(tmp_path / "sub_target_week2.json", ts)
    _write_score(tmp_path / "sub_other_week1.json", ts)

    report = retention.delete_subject("sub_target", [str(tmp_path)])

    assert report.deleted_count == 2
    assert not (tmp_path / "sub_target_week1.json").exists()
    assert (tmp_path / "sub_other_week1.json").exists()


def test_retention_policy_values_come_from_config():
    assert allowlist.retention_days("raw_events") == 90
    assert allowlist.retention_days("scores") == 395
    with pytest.raises(KeyError):
        allowlist.retention_days("no_such_bucket")


# ---------------------------------------------------------------------------
# Notice artifact -- cannot drift from the config it describes
# ---------------------------------------------------------------------------


def test_committed_notice_matches_regenerated_output():
    """Changing the allowlist without regenerating the notice fails the build."""
    with open(notice.NOTICE_PATH, encoding="utf-8") as f:
        committed = f.read()
    assert committed == notice.generate_notice(), (
        "docs/NOTICE.md is stale -- regenerate with `python -m src.governance.notice`"
    )


def test_notice_names_every_prohibited_category():
    text = notice.generate_notice().lower()
    for phrase in ("health", "keystroke", "location", "union", "salary"):
        assert phrase in text


def test_notice_lists_removed_fields_and_forbidden_uses():
    text = notice.generate_notice().lower()
    assert "sick_days" in text and "sentiment" in text
    assert "termination" in text and "pip" in text
