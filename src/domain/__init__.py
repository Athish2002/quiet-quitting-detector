# src/domain/ -- pure decision logic.
#
# The rule that makes this package worth having (PRODUCTION_EVOLUTION_PROMPT.md
# §4): `domain` imports nothing from `agents`, `platform`, `data_layer`, or any
# web framework. No file I/O, no network, no LLM. Everything here is a function
# of its arguments, which is what makes it property-testable and what lets both
# entrypoints share one implementation instead of drifting apart (blocker B6).
#
# An import-linter contract enforces the boundary in CI, because a rule this
# easy to break silently will be broken within a month otherwise.

from src.domain.fakes import FakeRiskScorer, FakeTrendEnricher
from src.domain.models import (
    Baseline,
    HistoryRecord,
    RiskAssessment,
    Severity,
    Signal,
    WeekMetrics,
)
from src.domain.protocols import RiskScorer, TrendEnricher
from src.domain.risk import (
    AT_RISK_THRESHOLD,
    HEALTHY_DECAY_WEEKS,
    SILENT_EXIT_THRESHOLD,
    WATCH_THRESHOLD,
    apply_recurrence_bonus,
    classify,
    compute_recurrence_bonus,
    compute_risk_index,
    next_healthy_streak,
)
from src.domain.signals import (
    CONSECUTIVE_WEEKS_REQUIRED,
    assign_severity,
    confirm_consecutive,
    confirm_signals,
    detect_week_flags,
    find_baseline,
)

__all__ = [
    "AT_RISK_THRESHOLD",
    "CONSECUTIVE_WEEKS_REQUIRED",
    "HEALTHY_DECAY_WEEKS",
    "SILENT_EXIT_THRESHOLD",
    "WATCH_THRESHOLD",
    "Baseline",
    "FakeRiskScorer",
    "FakeTrendEnricher",
    "HistoryRecord",
    "RiskAssessment",
    "RiskScorer",
    "Severity",
    "Signal",
    "TrendEnricher",
    "WeekMetrics",
    "apply_recurrence_bonus",
    "assign_severity",
    "classify",
    "compute_recurrence_bonus",
    "compute_risk_index",
    "confirm_consecutive",
    "confirm_signals",
    "detect_week_flags",
    "find_baseline",
    "next_healthy_streak",
]
