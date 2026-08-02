# src/api/schemas/operations.py
# Response models for the routes that are about the machine, not a person:
# ingest, pipeline runs, provider state, settings, the event log, and the
# destructive maintenance calls.
#
# Nothing here carries a name or an evaluation, which is why these models can be
# strict where the ones in people.py have to be forgiving -- every field below
# is produced by this codebase in the same process that serves it.

from __future__ import annotations

from typing import Literal

from pydantic import Field

from src.api.schemas.base import ResponseModel


class Ack(ResponseModel):
    """A mutation that either worked or raised. There is no partial success."""

    success: bool
    message: str = ""


class RunStarted(Ack):
    """A run was accepted. It has not finished -- poll GET /run/progress."""

    started: bool = True


class RunProgress(ResponseModel):
    """Where the current run has got to. All zeros when nothing is running."""

    running: bool
    scope: str | None = None
    done: int = 0
    total: int = 0
    current: str = ""
    #: Set when the last run ended badly. Never a raw provider error.
    error: str | None = None


class ApiCounters(ResponseModel):
    """Provider calls that succeeded, and ones the provider refused."""

    success: int = 0
    rejected: int = 0


class AppSettings(ResponseModel):
    local_only_mode: bool = False


class ExhaustedModel(ResponseModel):
    model: str
    cooldown_remaining_seconds: int = 0


class ProviderStatus(ResponseModel):
    """Which models are usable right now, not a cumulative counter."""

    fallback_sequence: list[str] = Field(default_factory=list)
    last_successful_model: str | None = None
    exhausted_models: list[ExhaustedModel] = Field(default_factory=list)
    #: True when every provider call is being skipped by choice.
    local_only_mode: bool = False


class EventLogEntry(ResponseModel):
    """One line of the operational event log.

    The field is `action`. It was `event_type` in the hand-written frontend
    types, which is the drift these models exist to make impossible.
    """

    timestamp: str = ""
    action: str = ""
    source: str = ""
    detail: str = ""
    success: bool = True


class ClearResult(Ack):
    files_removed: int = 0


class IngestResult(Ack):
    """The outcome of one ingest call, whichever source it came from."""

    #: True when an idempotency key replayed a stored result instead of
    #: ingesting again. The caller must be able to tell the two apart.
    idempotent_replay: bool = False


class DatabaseStats(ResponseModel):
    """The real local SQLite file. There is no corporate database behind this."""

    exists: bool = False
    total_rows: int = 0
    distinct_tables: int = 0
    distinct_weeks: int = 0
    file_size_bytes: int = 0
    last_ingested_at: str | None = None


class DatabaseSyncResult(IngestResult):
    source: str = "sqlite"
    db_stats: DatabaseStats | None = None


class BucketStats(ResponseModel):
    """The local bucket folder, and whether real AWS credentials are present."""

    exists: bool = False
    object_count: int = 0
    objects: list[str] = Field(default_factory=list)
    aws_credentials_configured: bool = False


class ObjectStoreSyncResult(IngestResult):
    #: Which of AWS S3, the local bucket, or a seeded demo object served this.
    source: str = ""


class ExtractedMetrics(ResponseModel):
    """What was read out of a free-text description. Nothing is inferred."""

    name: str
    tasks_completed: int = 0
    avg_response_time: float = 0.0
    after_hours_logins: int = 0
    weekly_hours: int = 40


class NaturalLanguageResult(ResponseModel):
    """Carries `source` because a rule-based extraction and a model's must not
    be indistinguishable to whoever reads the result."""

    success: bool
    source: Literal["llm", "local-fallback"]
    extracted: ExtractedMetrics
    idempotent_replay: bool = False


class MockDataResult(Ack):
    """The seed is returned so a cohort can be reproduced exactly."""

    seed: int
