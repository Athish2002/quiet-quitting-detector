# src/governance/purpose.py
# Phase 0 -- purpose binding.
#
# The framing constraint for this whole system is that punitive use must be
# structurally hard, not merely discouraged in documentation. That means the
# refusal lives in code: every scored record carries a `permitted_use`, and a
# consumer not registered for that purpose is refused and the refusal audited.
#
# FORBIDDEN_PURPOSES is deliberately enumerated rather than left implicit. A
# request naming one is not just unregistered -- it is a policy violation, and
# is logged as such, because someone attempting it is a signal in its own right.

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PermittedUse(StrEnum):
    """The complete set of purposes this system's output may serve."""

    MANAGER_SUPPORT_CONVERSATION = "manager_support_conversation"
    AGGREGATE_ORG_HEALTH = "aggregate_org_health"
    EMPLOYEE_SUBJECT_ACCESS = "employee_subject_access"
    MODEL_EVALUATION = "model_evaluation"


# Uses this system must never serve. Naming one is treated as an attempted
# policy breach, not a routine authorization failure.
FORBIDDEN_PURPOSES: frozenset[str] = frozenset(
    {
        "termination",
        "dismissal",
        "redundancy_selection",
        "performance_improvement_plan",
        "pip",
        "disciplinary",
        "compensation_review",
        "bonus_allocation",
        "promotion_denial",
        "ranking",
        "stack_ranking",
        "visa_or_immigration_decision",
        "employee_facing_score_display",
    }
)


class PurposeViolation(Exception):
    """Raised when a consumer requests data for a forbidden purpose."""


class PurposeDenied(Exception):
    """Raised when a consumer is simply not registered for a valid purpose."""


@dataclass(frozen=True)
class Consumer:
    consumer_id: str
    purposes: frozenset[PermittedUse]
    description: str


# Registry. In Phase 5 this moves behind RBAC with real identities; the shape
# is intentionally the same so the API layer swaps the source, not the logic.
_REGISTRY: dict[str, Consumer] = {
    "ui:manager-console": Consumer(
        "ui:manager-console",
        frozenset({PermittedUse.MANAGER_SUPPORT_CONVERSATION}),
        "Manager-facing console. Own direct reports only.",
    ),
    "ui:org-health": Consumer(
        "ui:org-health",
        frozenset({PermittedUse.AGGREGATE_ORG_HEALTH}),
        "Aggregate, k-anonymised org health view. No individual records.",
    ),
    "svc:subject-access": Consumer(
        "svc:subject-access",
        frozenset({PermittedUse.EMPLOYEE_SUBJECT_ACCESS}),
        "Serves an individual their own data on request (GDPR Art. 15).",
    ),
    "svc:model-eval": Consumer(
        "svc:model-eval",
        frozenset({PermittedUse.MODEL_EVALUATION}),
        "Offline evaluation and fairness measurement. Pseudonymous only.",
    ),
}


def register_consumer(consumer: Consumer) -> None:
    _REGISTRY[consumer.consumer_id] = consumer


def get_consumer(consumer_id: str) -> Consumer | None:
    return _REGISTRY.get(consumer_id)


def authorize(
    consumer_id: str,
    requested_use: str,
    *,
    subject_id: str | None = None,
    reason: str | None = None,
) -> PermittedUse:
    """Authorize a read, or refuse it. Every outcome is audited.

    Args:
        consumer_id: registered consumer making the request.
        requested_use: the purpose being asserted.
        subject_id: pseudonymous ID of the person the data is about.
        reason: free-text reason-for-access. Required for individual records --
            an unexplained lookup of a named person is exactly what the audit
            trail exists to surface.

    Raises:
        PurposeViolation: the purpose is categorically forbidden.
        PurposeDenied: unknown consumer, unknown purpose, or not registered
            for it; or an individual lookup with no stated reason.
    """
    from src.governance.audit import record_access

    normalised = (requested_use or "").strip().lower()

    def _deny(exc: Exception, outcome: str, detail: str):
        record_access(
            actor=consumer_id,
            action="authorize",
            subject_id=subject_id,
            purpose=normalised or "<none>",
            resource="score",
            outcome=outcome,
            detail=detail,
        )
        raise exc

    if normalised in FORBIDDEN_PURPOSES:
        _deny(
            PurposeViolation(
                f"Purpose {normalised!r} is forbidden. This system surfaces where "
                "support is needed; it must not inform adverse employment decisions."
            ),
            "policy_violation",
            f"forbidden purpose: {normalised}",
        )

    consumer = get_consumer(consumer_id)
    if consumer is None:
        _deny(
            PurposeDenied(f"Unknown consumer {consumer_id!r}."),
            "denied",
            "unregistered consumer",
        )

    try:
        use = PermittedUse(normalised)
    except ValueError:
        _deny(
            PurposeDenied(f"Unrecognised purpose {requested_use!r}."),
            "denied",
            "unrecognised purpose",
        )

    if use not in consumer.purposes:
        _deny(
            PurposeDenied(
                f"Consumer {consumer_id!r} is not registered for purpose {use.value!r}."
            ),
            "denied",
            f"not registered for {use.value}",
        )

    # Individual-record reads require a stated reason; aggregate reads do not,
    # because there is no individual to be accountable to.
    if subject_id is not None and use is not PermittedUse.AGGREGATE_ORG_HEALTH:
        if not (reason or "").strip():
            _deny(
                PurposeDenied(
                    "A reason-for-access is required when reading an individual's record."
                ),
                "denied",
                "missing reason-for-access",
            )

    record_access(
        actor=consumer_id,
        action="read_score",
        subject_id=subject_id,
        purpose=use.value,
        resource="score",
        outcome="allowed",
        detail=(reason or "").strip() or None,
    )
    return use
