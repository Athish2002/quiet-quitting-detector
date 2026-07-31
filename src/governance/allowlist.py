# src/governance/allowlist.py
# Phase 0 -- data minimization, enforced at the ingest boundary.
#
# Design rule: DEFAULT-DENY. A field reaches storage only if it is explicitly
# enumerated in config/data_allowlist.json. Filtering later (at query time, or
# in the model layer) is not equivalent: once a forbidden value is persisted it
# is in backups, in logs, and in scope for a subject-access request.
#
# Two distinct failure modes are handled differently on purpose:
#
#   * An *unknown* field is dropped quietly (normal: sources add columns).
#   * A *forbidden* field is dropped AND raises a loud, audited violation,
#     because its presence means an upstream system is sending us health data,
#     message content, or telemetry -- a problem that silence would hide.

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache

logger = logging.getLogger(__name__)

_CONFIG_PATH = os.environ.get(
    "DATA_ALLOWLIST_PATH",
    os.path.join(
        os.path.dirname(__file__), "..", "..", "config", "data_allowlist.json"
    ),
)


class ForbiddenFieldError(Exception):
    """Raised when an ingest payload carries a categorically prohibited field.

    Deliberately not a subclass of ValueError: callers must not be able to
    swallow this with a generic `except ValueError` used for parsing.
    """

    def __init__(self, violations: list[FieldViolation]):
        self.violations = violations
        detail = "; ".join(f"{v.field_name} ({v.category})" for v in violations)
        super().__init__(f"Prohibited field(s) present at ingest: {detail}")


@dataclass(frozen=True)
class FieldViolation:
    field_name: str
    category: str
    matched_pattern: str


@dataclass
class FilterResult:
    """Outcome of filtering one record."""

    accepted: dict = field(default_factory=dict)
    dropped_unknown: list[str] = field(default_factory=list)
    violations: list[FieldViolation] = field(default_factory=list)

    @property
    def had_violation(self) -> bool:
        return bool(self.violations)


@lru_cache(maxsize=1)
def load_policy() -> dict:
    """Load and cache the allowlist config.

    Cached because it is consulted per-record on every ingest path; call
    `load_policy.cache_clear()` in tests that patch the config.
    """
    with open(os.path.abspath(_CONFIG_PATH), encoding="utf-8") as f:
        return json.load(f)


def permitted_fields() -> dict[str, dict]:
    return load_policy()["permitted_fields"]


@lru_cache(maxsize=1)
def _alias_index() -> dict[str, str]:
    """Reverse map: any accepted header spelling -> canonical field name.

    Sources spell the same field a dozen ways (`employee_name`, `Employee Name`,
    `first_name`). Matching only canonical names would drop legitimate columns as
    "unknown", so the allowlist resolves aliases from the same config that
    documents them -- keeping one source of truth rather than a second copy
    drifting alongside `ingestion.COLUMN_ALIASES`.
    """
    index: dict[str, str] = {}
    for canonical, spec in permitted_fields().items():
        index[_norm(canonical)] = canonical
        for alias in spec.get("aliases", []):
            index[_norm(alias)] = canonical
    return index


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def resolve_canonical(field_name: str) -> str | None:
    """Canonical name for an incoming header, or None if not allowlisted."""
    return _alias_index().get(_norm(field_name))


def is_permitted(field_name: str) -> bool:
    return resolve_canonical(field_name) is not None


def risk_scoring_fields() -> set[str]:
    """Fields allowed to influence a retention-risk score.

    Narrower than `permitted_fields`: identifiers, time indices and
    wellbeing-only signals are permitted to exist but barred from raising risk.
    Phase 2/3 must source model inputs from here, never from the raw record.
    """
    return {
        name
        for name, spec in permitted_fields().items()
        if spec.get("risk_scoring") is True
    }


def wellbeing_only_fields() -> set[str]:
    """Fields that may only ever LOWER concern (e.g. burnout check-ins).

    Structurally separated so a future change cannot quietly promote one into
    the risk model -- see `after_hours_logins`, which penalises non-US
    timezones and caregivers if allowed to raise risk.
    """
    return {
        name
        for name, spec in permitted_fields().items()
        if spec.get("wellbeing_only") is True
    }


def retention_days(bucket: str) -> int:
    try:
        return int(load_policy()["retention_days"][bucket])
    except (KeyError, TypeError, ValueError) as exc:
        raise KeyError(f"No retention policy configured for bucket {bucket!r}") from exc


def _forbidden_categories() -> dict[str, list[str]]:
    raw = load_policy().get("forbidden_patterns", {})
    return {k: v for k, v in raw.items() if not k.startswith("$")}


def classify_forbidden(field_name: str) -> FieldViolation | None:
    """Return a violation if `field_name` matches any prohibited pattern.

    Matching is on a normalised name (case-folded, separators stripped) so
    `Sick Days`, `sick-days` and `sickDays` are all caught by the same pattern.
    """
    normalised = re.sub(r"[^a-z0-9]", "", field_name.lower())
    for category, patterns in _forbidden_categories().items():
        for pattern in patterns:
            if re.sub(r"[^a-z0-9]", "", pattern.lower()) in normalised:
                return FieldViolation(field_name, category, pattern)
    return None


def filter_record(record: dict, *, source: str, strict: bool = True) -> FilterResult:
    """Apply the allowlist to one incoming record.

    Args:
        record: raw field-name -> value mapping from a connector.
        source: connector identifier, for the audit trail.
        strict: raise ForbiddenFieldError on a prohibited field (default).
            Set False for bulk backfills that should quarantine and continue
            rather than abort the whole window -- the violation is still
            recorded and the field still never persists.

    Returns:
        FilterResult carrying only permitted fields.
    """
    result = FilterResult()

    for key, value in record.items():
        # Forbidden check runs FIRST and on the raw name: an alias must never
        # be able to smuggle a prohibited field past the pattern match.
        violation = classify_forbidden(key)
        if violation is not None:
            result.violations.append(violation)
            continue  # never persisted, regardless of strict mode
        if resolve_canonical(key) is not None:
            result.accepted[key] = value
        else:
            result.dropped_unknown.append(key)

    if result.violations:
        # Loud by design: this means an upstream source is sending prohibited
        # data. Field names only -- never log the values themselves.
        logger.error(
            "PROHIBITED FIELD(S) REJECTED AT INGEST from source=%s: %s",
            source,
            ", ".join(f"{v.field_name}[{v.category}]" for v in result.violations),
        )
        _record_violation_audit(source, result.violations)
        if strict:
            raise ForbiddenFieldError(result.violations)

    if result.dropped_unknown:
        logger.info(
            "Dropped %d non-allowlisted field(s) from source=%s: %s",
            len(result.dropped_unknown),
            source,
            ", ".join(sorted(result.dropped_unknown)),
        )

    return result


def _record_violation_audit(source: str, violations: list[FieldViolation]) -> None:
    """Best-effort audit of a policy violation.

    Imported lazily to keep this module usable (and testable) without the
    audit database present; a failure here must never mask the violation
    itself, which has already been logged and raised.
    """
    try:
        from src.governance.audit import record_access

        record_access(
            actor="system:ingest",
            action="policy_violation",
            subject_id=None,
            purpose="data_minimization_enforcement",
            resource=f"source:{source}",
            outcome="rejected",
            detail=", ".join(f"{v.field_name}[{v.category}]" for v in violations),
        )
    except Exception:  # pragma: no cover - audit must never break ingest
        logger.debug("Could not write violation audit entry.", exc_info=True)
