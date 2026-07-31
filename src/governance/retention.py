# src/governance/retention.py
# Phase 0 -- retention and real deletion.
#
# TTLs come from config/data_allowlist.json so the notice artifact and the
# enforcement share one source of truth. Deletion is *real*: files are removed
# from disk and rows removed from the database. Tombstoning would leave the
# data recoverable and would not satisfy a deletion request.
#
# The audit log is the one bucket with a long TTL (7y default) and its own
# purge path, because it is the evidence that the other purges happened.

from __future__ import annotations

import glob
import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from src.governance.allowlist import retention_days

logger = logging.getLogger(__name__)


@dataclass
class PurgeReport:
    bucket: str
    cutoff: str
    deleted: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def deleted_count(self) -> int:
        return len(self.deleted)

    def as_dict(self) -> dict:
        return {
            "bucket": self.bucket,
            "cutoff": self.cutoff,
            "deleted_count": self.deleted_count,
            "deleted": self.deleted,
            "errors": self.errors,
        }


def _cutoff(bucket: str, now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now - timedelta(days=retention_days(bucket))


def _record_mtime(path: str) -> datetime:
    return datetime.fromtimestamp(os.path.getmtime(path), tz=UTC)


def purge_expired_files(
    directory: str,
    bucket: str,
    *,
    pattern: str = "*.json",
    now: datetime | None = None,
    dry_run: bool = False,
) -> PurgeReport:
    """Delete files in `directory` older than the bucket's TTL.

    Uses each record's own timestamp where present (scores carry one), falling
    back to filesystem mtime. Reading the embedded timestamp matters: copying
    or restoring files refreshes mtime and would otherwise silently extend
    retention beyond the policy.
    """
    cut = _cutoff(bucket, now)
    report = PurgeReport(bucket=bucket, cutoff=cut.isoformat())

    if not os.path.isdir(directory):
        return report

    for path in glob.glob(os.path.join(directory, pattern)):
        try:
            ts = _embedded_timestamp(path) or _record_mtime(path)
            if ts < cut:
                if not dry_run:
                    os.remove(path)
                report.deleted.append(os.path.basename(path))
        except OSError as exc:
            report.errors.append(f"{os.path.basename(path)}: {exc}")

    if report.deleted and not dry_run:
        logger.info(
            "Retention purge (%s): deleted %d record(s) older than %s.",
            bucket,
            report.deleted_count,
            cut.date().isoformat(),
        )
        _audit_purge(report)
    return report


def _embedded_timestamp(path: str) -> datetime | None:
    """Best-effort read of a record's own timestamp."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    for key in ("timestamp", "scored_at", "created_at", "ts"):
        raw = data.get(key)
        if isinstance(raw, str):
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
            except ValueError:
                continue
    return None


def purge_expired_audit(
    db_path: str | None = None, *, now: datetime | None = None
) -> PurgeReport:
    """Purge audit rows past their (long) TTL.

    The append-only triggers block DELETE by design, so this drops them inside
    a transaction and restores them immediately. That keeps ad-hoc deletion
    impossible while still allowing the one sanctioned, audited purge path.
    """
    from src.governance.audit import AUDIT_DB_PATH, _connect

    path = db_path or AUDIT_DB_PATH
    cut = _cutoff("audit_log", now)
    report = PurgeReport(bucket="audit_log", cutoff=cut.isoformat())

    if not os.path.exists(path):
        return report

    try:
        with _connect(path) as conn:
            conn.execute("DROP TRIGGER IF EXISTS access_log_no_delete")
            try:
                cur = conn.execute(
                    "DELETE FROM access_log WHERE ts < ?", (cut.isoformat(),)
                )
                report.deleted = (
                    [f"{cur.rowcount} audit row(s)"] if cur.rowcount else []
                )
            finally:
                conn.execute(
                    "CREATE TRIGGER IF NOT EXISTS access_log_no_delete "
                    "BEFORE DELETE ON access_log BEGIN "
                    "SELECT RAISE(ABORT, 'access_log is append-only: DELETE is forbidden'); "
                    "END"
                )
    except sqlite3.Error as exc:
        report.errors.append(str(exc))
    return report


def _audit_purge(report: PurgeReport) -> None:
    try:
        from src.governance.audit import record_access

        record_access(
            actor="system:retention",
            action="purge",
            purpose="model_evaluation",
            resource=report.bucket,
            outcome="allowed",
            detail=f"deleted {report.deleted_count} record(s) older than {report.cutoff}",
        )
    except Exception:  # pragma: no cover
        logger.debug("Could not audit retention purge.", exc_info=True)


def delete_subject(subject_id: str, directories: list[str]) -> PurgeReport:
    """Erase every stored record for one individual (GDPR Art. 17).

    Matches on the pseudonymous surrogate ID prefix used in record filenames.
    The audit log is intentionally NOT purged here: it records *who accessed
    what*, is the evidence this deletion occurred, and is retained under its
    own legal basis.
    """
    report = PurgeReport(bucket="subject_erasure", cutoff=subject_id)
    for directory in directories:
        if not os.path.isdir(directory):
            continue
        for path in glob.glob(os.path.join(directory, f"{subject_id}_*.json")):
            try:
                os.remove(path)
                report.deleted.append(os.path.basename(path))
            except OSError as exc:
                report.errors.append(f"{os.path.basename(path)}: {exc}")

    try:
        from src.governance.audit import record_access

        record_access(
            actor="system:erasure",
            action="delete_subject",
            subject_id=subject_id,
            purpose="employee_subject_access",
            resource="all_stores",
            outcome="allowed",
            detail=f"erased {report.deleted_count} record(s)",
        )
    except Exception:  # pragma: no cover
        logger.debug("Could not audit subject erasure.", exc_info=True)
    return report
