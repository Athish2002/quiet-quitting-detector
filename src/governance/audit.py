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

import hashlib
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
    detail      TEXT,
    -- Phase 4 (7): hash chain. Each row commits to its own contents AND to the
    -- previous row's hash, so removing or editing an entry breaks every hash
    -- after it. The DB triggers below already block UPDATE and DELETE, but a
    -- trigger only protects the log from someone using this connection --
    -- anyone with the file can rewrite it. The chain makes that DETECTABLE,
    -- which is what "tamper-evident" actually means and what the triggers
    -- alone cannot give.
    prev_hash   TEXT,
    entry_hash  TEXT
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


#: Columns added after the table first shipped. `CREATE TABLE IF NOT EXISTS`
#: does nothing to an existing table, so without this an audit.db created before
#: Phase 4 keeps its old shape and EVERY write fails on the missing column --
#: silently, because record_access() swallows exceptions by design. The log would
#: simply stop recording, which is the exact failure the module docstring calls a
#: compliance failure in its own right. Found by running the app, not by a test:
#: tests use fresh temporary databases and never meet an old one.
_ADDED_COLUMNS = {
    "prev_hash": "TEXT",
    "entry_hash": "TEXT",
}


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(access_log)")}
    if not existing:
        return  # fresh database; the schema script handles it

    for column, sql_type in _ADDED_COLUMNS.items():
        if column not in existing:
            logger.warning("Adding missing audit column %s to an existing log.", column)
            conn.execute(f"ALTER TABLE access_log ADD COLUMN {column} {sql_type}")


def _ensure_schema(conn: sqlite3.Connection, path: str) -> None:
    if path in _initialised:
        return
    with _init_lock:
        if path in _initialised:
            return
        conn.executescript(_SCHEMA)
        _migrate(conn)
        conn.commit()
        _initialised.add(path)


#: First link in the chain. A fixed, published value: the point of the chain is
#: detecting modification, not secrecy, and a secret seed would only mean the
#: log could not be verified by the person it is about.
GENESIS_HASH = "0" * 64


def _entry_hash(
    prev_hash: str,
    ts: str,
    actor: str,
    action: str,
    subject_id: str | None,
    purpose: str,
    resource: str | None,
    outcome: str,
    detail: str | None,
) -> str:
    """SHA-256 over the previous hash and this entry's fields.

    Field separator is \\x1f (unit separator), which cannot occur in the values,
    so two different entries cannot produce the same digest by concatenating
    differently -- "ab" + "c" and "a" + "bc" would otherwise collide.
    """
    payload = "\x1f".join(
        [
            prev_hash,
            ts,
            actor,
            action,
            subject_id or "",
            purpose,
            resource or "",
            outcome,
            detail or "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_chain(db_path: str | None = None) -> tuple[bool, int | None]:
    """Recompute the whole chain. Returns (intact, first_broken_row_id).

    This is the control that makes the audit log evidence rather than a record.
    Without it, "append-only" holds only against code using this module; anyone
    with the database file can edit a row and nothing would ever say so.
    """
    try:
        with _connect(db_path) as conn:
            rows = conn.execute("SELECT * FROM access_log ORDER BY id ASC").fetchall()
    except Exception:
        logger.error("Audit verification failed to read the log.", exc_info=True)
        return False, None

    expected_prev = GENESIS_HASH
    chain_started = False

    for row in rows:
        entry = dict(row)

        # Rows written before hash-chaining existed carry no hash. They are
        # unverifiable, not evidence of tampering, and are skipped -- but only
        # while they PRECEDE the chain. Once a chained row has been seen, a
        # missing hash is somebody removing one, and is reported as a break.
        if entry.get("entry_hash") is None:
            if chain_started:
                return False, entry["id"]
            continue

        if not chain_started:
            # The chain begins wherever the first hashed row is; it commits to
            # GENESIS or to whatever it recorded at the time.
            expected_prev = entry.get("prev_hash") or GENESIS_HASH
            chain_started = True

        if entry.get("prev_hash") != expected_prev:
            return False, entry["id"]

        recomputed = _entry_hash(
            expected_prev,
            entry["ts"],
            entry["actor"],
            entry["action"],
            entry["subject_id"],
            entry["purpose"],
            entry["resource"],
            entry["outcome"],
            entry["detail"],
        )
        if recomputed != entry.get("entry_hash"):
            return False, entry["id"]

        expected_prev = recomputed

    return True, None


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
            row = conn.execute(
                "SELECT entry_hash FROM access_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
            prev_hash = (row["entry_hash"] if row else None) or GENESIS_HASH

            ts = datetime.now(UTC).isoformat()
            entry_hash = _entry_hash(
                prev_hash,
                ts,
                actor,
                action,
                subject_id,
                purpose,
                resource,
                outcome,
                detail,
            )

            conn.execute(
                "INSERT INTO access_log "
                "(ts, actor, action, subject_id, purpose, resource, outcome, detail, "
                " prev_hash, entry_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ts,
                    actor,
                    action,
                    subject_id,
                    purpose,
                    resource,
                    outcome,
                    detail,
                    prev_hash,
                    entry_hash,
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
