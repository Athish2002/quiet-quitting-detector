# src/evolution/intervention_store.py
# Persistence for manager interventions (see src/domain/intervention.py).
#
# Same shape and same constraints as feedback_store.py: SQLite, one record per
# (subject, week), and NO free-text column. The absence of that column is the
# control -- it is what stops this table from becoming a record of what managers
# said to their reports.
#
# There is also deliberately no `manager_id`. Storing it would make per-manager
# effectiveness a one-line query away, and the reason that must not exist is set
# out at length in the domain module. The attribution that is genuinely useful --
# which KINDS of support tend to be followed by recovery -- needs no such column.

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime

from src.config import get_settings
from src.domain.intervention import InterventionRecord, InterventionType

logger = logging.getLogger(__name__)


#: Resolved per call, never captured at import -- see src/config.py.
def default_db_path() -> str:
    return get_settings().intervention_db


_init_lock = threading.Lock()
_initialised: set[str] = set()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS interventions (
    subject_id    TEXT    NOT NULL,
    week          INTEGER NOT NULL,
    intervention  TEXT    NOT NULL,
    recorded_at   TEXT    NOT NULL,
    PRIMARY KEY (subject_id, week)
);
CREATE INDEX IF NOT EXISTS idx_intervention_type ON interventions(intervention);
"""


class InterventionStore:
    """What kind of action a manager took, and when. Never what they said."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or default_db_path()

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

    def record(self, intervention: InterventionRecord) -> InterventionRecord:
        stamped = intervention.model_copy(
            update={
                "recorded_at": intervention.recorded_at or datetime.now(UTC).isoformat()
            }
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO interventions "
                "(subject_id, week, intervention, recorded_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(subject_id, week) DO UPDATE SET "
                " intervention = excluded.intervention, "
                " recorded_at = excluded.recorded_at",
                (
                    stamped.subject_id,
                    stamped.week,
                    stamped.intervention.value,
                    stamped.recorded_at,
                ),
            )
        return stamped

    def all(self, *, subject_id: str | None = None) -> list[InterventionRecord]:
        where, params = (
            ("WHERE subject_id = ?", [subject_id]) if subject_id else ("", [])
        )
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    f"SELECT * FROM interventions {where} ORDER BY week ASC", params
                ).fetchall()
        except Exception:
            logger.error("Intervention query failed.", exc_info=True)
            return []

        records: list[InterventionRecord] = []
        for row in rows:
            entry = dict(row)
            try:
                kind = InterventionType(entry["intervention"])
            except ValueError:
                logger.warning("Unknown intervention type in store; skipping row.")
                continue
            records.append(
                InterventionRecord(
                    subject_id=entry["subject_id"],
                    week=entry["week"],
                    intervention=kind,
                    recorded_at=entry["recorded_at"],
                )
            )
        return records

    def for_subject(self, subject_id: str) -> list[InterventionRecord]:
        return self.all(subject_id=subject_id)
