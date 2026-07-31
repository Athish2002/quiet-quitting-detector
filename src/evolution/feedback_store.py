# src/evolution/feedback_store.py
# Persistence for manager feedback (PRODUCTION_EVOLUTION_PROMPT.md 6.2).
#
# SQLite, matching src/governance/audit.py: already a dependency, no server, and
# real engine-level constraints rather than conventions held in application code.
#
# Two properties this store enforces that a JSON file could not:
#
#   1. One verdict per (subject, week). A manager changing their mind REPLACES
#      their verdict rather than adding a second one. Without this, calibration
#      silently weights whoever clicked most, and "83% accurate" would describe
#      clicking behaviour rather than accuracy.
#
#   2. No free text. There is no column for it. CONTEXT.md rule 5 forbids
#      opinions and health information in agent memory, and a notes field on a
#      form about an employee is where exactly that ends up -- not through bad
#      faith, but because a manager trying to be helpful writes "she's been
#      struggling since her dad got ill". The schema makes it impossible.

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime

from src.domain.feedback import FeedbackReason, FeedbackRecord, FeedbackVerdict

logger = logging.getLogger(__name__)

DEFAULT_FEEDBACK_DB = os.environ.get(
    "FEEDBACK_DB_PATH", os.path.join("data", "feedback.db")
)

_init_lock = threading.Lock()
_initialised: set[str] = set()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS manager_feedback (
    subject_id                TEXT    NOT NULL,
    week                      INTEGER NOT NULL,
    predicted_score           INTEGER NOT NULL,
    predicted_classification  TEXT    NOT NULL,
    verdict                   TEXT    NOT NULL,
    reason                    TEXT    NOT NULL,
    model_version             TEXT    NOT NULL,
    recorded_at               TEXT    NOT NULL,
    PRIMARY KEY (subject_id, week)
);
CREATE INDEX IF NOT EXISTS idx_feedback_version ON manager_feedback(model_version);
CREATE INDEX IF NOT EXISTS idx_feedback_time    ON manager_feedback(recorded_at);
"""


class FeedbackStore:
    """Append-or-replace store of manager verdicts, keyed by (subject, week)."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or DEFAULT_FEEDBACK_DB

    @contextmanager
    def _connect(self):
        parent = os.path.dirname(os.path.abspath(self.db_path))
        os.makedirs(parent, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            self._ensure_schema(conn)
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        if self.db_path in _initialised:
            return
        with _init_lock:
            if self.db_path in _initialised:
                return
            conn.executescript(_SCHEMA)
            conn.commit()
            _initialised.add(self.db_path)

    def record(self, feedback: FeedbackRecord) -> FeedbackRecord:
        """Store one verdict, replacing any earlier verdict for the same week.

        Raises nothing on a duplicate: a manager revising their opinion is the
        expected case, not an error, and the second answer is the one that is
        true. The audit log in src/governance/audit.py is where the fact that
        they changed it is recorded.
        """
        stamped = feedback.model_copy(
            update={
                "recorded_at": feedback.recorded_at or datetime.now(UTC).isoformat()
            }
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO manager_feedback "
                "(subject_id, week, predicted_score, predicted_classification, "
                " verdict, reason, model_version, recorded_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(subject_id, week) DO UPDATE SET "
                " predicted_score = excluded.predicted_score, "
                " predicted_classification = excluded.predicted_classification, "
                " verdict = excluded.verdict, "
                " reason = excluded.reason, "
                " model_version = excluded.model_version, "
                " recorded_at = excluded.recorded_at",
                (
                    stamped.subject_id,
                    stamped.week,
                    stamped.predicted_score,
                    stamped.predicted_classification,
                    stamped.verdict.value,
                    stamped.reason.value,
                    stamped.model_version,
                    stamped.recorded_at,
                ),
            )
        return stamped

    def all(
        self, *, subject_id: str | None = None, model_version: str | None = None
    ) -> list[FeedbackRecord]:
        """Every stored verdict, optionally narrowed. Oldest first."""
        clauses, params = [], []
        if subject_id is not None:
            clauses.append("subject_id = ?")
            params.append(subject_id)
        if model_version is not None:
            clauses.append("model_version = ?")
            params.append(model_version)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        try:
            with self._connect() as conn:
                rows = conn.execute(
                    f"SELECT * FROM manager_feedback {where} "
                    "ORDER BY recorded_at ASC, week ASC",
                    params,
                ).fetchall()
        except Exception:
            logger.error("Feedback query failed.", exc_info=True)
            return []

        return [self._to_record(dict(row)) for row in rows]

    def for_subject(self, subject_id: str) -> list[FeedbackRecord]:
        return self.all(subject_id=subject_id)

    def count(self) -> int:
        try:
            with self._connect() as conn:
                return int(
                    conn.execute("SELECT COUNT(*) FROM manager_feedback").fetchone()[0]
                )
        except Exception:
            logger.error("Feedback count failed.", exc_info=True)
            return 0

    @staticmethod
    def _to_record(row: dict) -> FeedbackRecord:
        """Rebuild a typed record, tolerating values written by an older schema.

        An unrecognised verdict or reason falls back rather than raising: a
        single unreadable row must not take down the calibration view, which is
        the thing that would tell an operator something is wrong.
        """
        try:
            verdict = FeedbackVerdict(row["verdict"])
        except ValueError:
            logger.warning("Unknown feedback verdict in store; treating as not stated.")
            verdict = FeedbackVerdict.NOT_ACCURATE
        try:
            reason = FeedbackReason(row["reason"])
        except ValueError:
            reason = FeedbackReason.NOT_STATED

        return FeedbackRecord(
            subject_id=row["subject_id"],
            week=row["week"],
            predicted_score=row["predicted_score"],
            predicted_classification=row["predicted_classification"],
            verdict=verdict,
            reason=reason,
            model_version=row["model_version"],
            recorded_at=row["recorded_at"],
        )
