# src/governance/audit.py
# Phase 0 -- append-only access audit log.
#
# The pre-existing data/audit_log.jsonl records *system* events (ingest,
# pipeline runs). It cannot answer the question Phase 0 actually requires:
# "who viewed whose risk score, when, and why". This module adds that, and is
# the record a subject-access request is served from.
#
# Storage choice: SQLite. It is already a project dependency, needs no server,
# and -- unlike a JSONL file -- gives queryable subject/actor/time filtering
# plus real DB-level immutability. UPDATE and DELETE are blocked by triggers,
# so append-only is enforced by the engine rather than by convention. Phase 1/2
# migrates to Postgres alongside the feature store; the schema is portable.

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

AUDIT_DB_PATH = os.environ.get("AUDIT_DB_PATH", os.path.join("data", "audit.db"))

_init_lock = threading.Lock()
_initialised: set[str] = set()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS access_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    actor       TEXT    NOT NULL,
    action      TEXT    NOT NULL,
    subject_id  TEXT,
    purpose     TEXT    NOT NULL,
    resource    TEXT,
    outcome     TEXT    NOT NULL,
    detail      TEXT
);
CREATE INDEX IF NOT EXISTS idx_access_subject ON access_log(subject_id);
CREATE INDEX IF NOT EXISTS idx_access_actor   ON access_log(actor);
CREATE INDEX IF NOT EXISTS idx_access_ts      ON access_log(ts);

-- Append-only, enforced by the engine. Retention purges are the sole
-- exception and run via `purge_expired()`, which drops the trigger inside a
-- transaction, deletes, and restores it -- so an ad-hoc DELETE still fails.
CREATE TRIGGER IF NOT EXISTS access_log_no_update
BEFORE UPDATE ON access_log
BEGIN
    SELECT RAISE(ABORT, 'access_log is append-only: UPDATE is forbidden');
END;

CREATE TRIGGER IF NOT EXISTS access_log_no_delete
BEFORE DELETE ON access_log
BEGIN
    SELECT RAISE(ABORT, 'access_log is append-only: DELETE is forbidden');
END;
"""


@contextmanager
def _connect(db_path: str | None = None):
    path = db_path or AUDIT_DB_PATH
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        _ensure_schema(conn, path)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ensure_schema(conn: sqlite3.Connection, path: str) -> None:
    if path in _initialised:
        return
    with _init_lock:
        if path in _initialised:
            return
        conn.executescript(_SCHEMA)
        conn.commit()
        _initialised.add(path)


def record_access(
    *,
    actor: str,
    action: str,
    purpose: str,
    subject_id: str | None = None,
    resource: str | None = None,
    outcome: str = "allowed",
    detail: str | None = None,
    db_path: str | None = None,
) -> None:
    """Append one access event.

    Never raises: an audit write failing must not break the request it
    describes. It is logged at ERROR because a silently missing audit trail is
    itself a compliance failure someone needs to see.

    `subject_id` must be the pseudonymous surrogate ID, never a real name.
    """
    try:
        with _connect(db_path) as conn:
            conn.execute(
                "INSERT INTO access_log "
                "(ts, actor, action, subject_id, purpose, resource, outcome, detail) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(UTC).isoformat(),
                    actor,
                    action,
                    subject_id,
                    purpose,
                    resource,
                    outcome,
                    detail,
                ),
            )
    except Exception:
        logger.error("AUDIT WRITE FAILED (%s/%s)", actor, action, exc_info=True)


def query_access(
    *,
    subject_id: str | None = None,
    actor: str | None = None,
    limit: int = 500,
    db_path: str | None = None,
) -> list[dict]:
    """Query the audit trail, newest first."""
    clauses, params = [], []
    if subject_id is not None:
        clauses.append("subject_id = ?")
        params.append(subject_id)
    if actor is not None:
        clauses.append("actor = ?")
        params.append(actor)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(int(limit))
    try:
        with _connect(db_path) as conn:
            rows = conn.execute(
                f"SELECT * FROM access_log {where} ORDER BY id DESC LIMIT ?", params
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        logger.error("Audit query failed.", exc_info=True)
        return []


def export_subject_access_request(subject_id: str, db_path: str | None = None) -> dict:
    """Produce the GDPR Art. 15 record for one individual.

    Answers "who looked at my data, when, and for what stated reason" in a
    form that can be handed to the person directly.
    """
    entries = query_access(subject_id=subject_id, limit=100_000, db_path=db_path)
    return {
        "subject_id": subject_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "access_event_count": len(entries),
        "events": entries,
        "note": (
            "Each entry records an access to data held about you, the stated "
            "purpose, and the outcome. Identifiers are pseudonymous surrogate "
            "IDs."
        ),
    }
