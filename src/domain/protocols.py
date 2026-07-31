# src/domain/protocols.py
# The seams that let the whole pipeline run without a network.
#
# PRODUCTION_EVOLUTION_PROMPT.md 6.3: "Every agent sits behind a Protocol. A
# FakeAgent returning fixed outputs makes the entire pipeline testable with zero
# network calls. CI must never call a real LLM."
#
# These are structural (typing.Protocol), not base classes: the existing agent
# modules satisfy them by shape and need no inheritance, so nothing in the LLM
# path had to be rewritten to gain a test seam.
#
# Note what is deliberately NOT behind a Protocol: signal detection and the score
# bands. Those are pure functions in this package and must have exactly one
# implementation -- making them swappable would invite a second, divergent copy,
# which is the blocker (B6) this package exists to close.

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.domain.models import HistoryRecord, RiskAssessment, Signal


@runtime_checkable
class TrendEnricher(Protocol):
    """Turns confirmed signals into supportive prose.

    Enrichment is presentation only. An implementation may add or reword
    `details`; it must not change `signal_name`, `weeks_detected` or `severity`,
    because those are evidence and an LLM is not entitled to revise evidence.
    """

    def enrich(self, first_name: str, signals: list[Signal]) -> list[Signal]: ...


@runtime_checkable
class RiskScorer(Protocol):
    """Produces the risk assessment for one employee-week.

    `history` is the employee's own prior weeks, chronologically ordered and
    already filtered to weeks strictly before `week_number` -- an implementation
    must never see a future week.

    The returned score is PRE-recurrence: the caller applies the recurrence
    bonus and healthy-streak decay from `domain.risk`, so that rule has one
    implementation regardless of who did the scoring.
    """

    def score(
        self,
        first_name: str,
        signals: list[Signal],
        week_number: int,
        history: list[HistoryRecord],
    ) -> RiskAssessment: ...
