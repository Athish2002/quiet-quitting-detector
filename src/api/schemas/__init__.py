# src/api/schemas/
# Response models -- what each JSON handler actually returns.
#
# `frontend/src/api/schema.ts` is generated from the OpenAPI document these
# models feed. Until they existed every handler was annotated `-> dict`, so the
# generated types described every response as an open object: paths, methods and
# request bodies were checked against the backend, response FIELDS were
# hand-copied into `frontend/src/api/types.ts`, and nothing compared the two.
#
# They had already drifted. `HistoryEvent.event_type` was a field no handler has
# ever returned -- the event log writes `action` -- so the History page rendered
# an em-dash in the Type column of every row, and the frontend test asserted
# against a mock that repeated the same mistake. Nothing failed, because there
# was nothing here that could fail.
#
# Split in two along the line that matters: `people` holds everything that
# describes a person and therefore has to survive whatever an older run or a
# provider wrote to disk; `operations` holds everything about the machine, which
# this process produces itself and can be strict about. Importers should not
# care -- everything is re-exported here.
#
# One convention worth knowing before editing: list fields default to `= []`
# rather than `Field(default_factory=list)`. Pydantic deep-copies mutable
# defaults per instance, so both are safe, but only the literal reaches the JSON
# schema as `"default": []` -- and without that the generated TypeScript marks
# the field OPTIONAL, forcing every consumer to guard against an absence the
# server cannot produce.

from src.api.schemas.operations import (
    Ack,
    ApiCounters,
    AppSettings,
    BucketStats,
    ClearResult,
    DatabaseStats,
    DatabaseSyncResult,
    EventLogEntry,
    ExhaustedModel,
    ExtractedMetrics,
    IngestResult,
    MockDataResult,
    NaturalLanguageResult,
    ObjectStoreSyncResult,
    ProviderStatus,
    RunProgress,
    RunStarted,
)
from src.api.schemas.people import (
    BriefingView,
    EmployeeSummary,
    EmployeeWeek,
    FeedbackAck,
    InterventionAck,
    InterventionExample,
    InterventionOutcomes,
    InterventionTypes,
    ModelList,
    RiskData,
    Signal,
    SimulationResult,
)

# Re-exported rather than redefined: these already exist as the domain's own
# typed objects, and a second copy here would be a second thing to keep in step.
from src.domain.feedback import CalibrationReport
from src.domain.intervention import InterventionAggregate
from src.domain.models import Attribution
from src.evolution.calibration import DriftView
from src.evolution.registry import ModelVersion

__all__ = [
    "Ack",
    "ApiCounters",
    "AppSettings",
    "Attribution",
    "BriefingView",
    "BucketStats",
    "CalibrationReport",
    "ClearResult",
    "DatabaseStats",
    "DatabaseSyncResult",
    "DriftView",
    "EmployeeSummary",
    "EmployeeWeek",
    "EventLogEntry",
    "ExhaustedModel",
    "ExtractedMetrics",
    "FeedbackAck",
    "IngestResult",
    "InterventionAck",
    "InterventionAggregate",
    "InterventionExample",
    "InterventionOutcomes",
    "InterventionTypes",
    "MockDataResult",
    "ModelList",
    "ModelVersion",
    "NaturalLanguageResult",
    "ObjectStoreSyncResult",
    "ProviderStatus",
    "RiskData",
    "RunProgress",
    "RunStarted",
    "Signal",
    "SimulationResult",
]
