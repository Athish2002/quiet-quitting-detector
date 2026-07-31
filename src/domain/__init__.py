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

from src.domain.attribution import attribute, leading_metric
from src.domain.changepoint import cusum_shift_week, longest_consecutive_run
from src.domain.cohort import cohort_shift, is_shared_confound, remove_shared_confound
from src.domain.fakes import FakeRiskScorer, FakeTrendEnricher
from src.domain.models import (
    Attribution,
    Baseline,
    Confidence,
    Deviation,
    HistoryRecord,
    MetricBaseline,
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
    build_personal_baselines,
    confirm_consecutive,
    confirm_signals,
    confirm_signals_threshold,
    detect_week_flags,
    find_baseline,
)
from src.domain.statistics import (
    ROBUST_Z_THRESHOLD,
    Direction,
    build_baseline,
    effect_size,
    is_significant,
    robust_z,
)
from src.domain.uncertainty import (
    assess_confidence,
    assess_from_timeline,
    score_range,
    suppresses_briefing,
)

__all__ = [
    "AT_RISK_THRESHOLD",
    "CONSECUTIVE_WEEKS_REQUIRED",
    "HEALTHY_DECAY_WEEKS",
    "ROBUST_Z_THRESHOLD",
    "SILENT_EXIT_THRESHOLD",
    "WATCH_THRESHOLD",
    "Attribution",
    "Baseline",
    "Confidence",
    "Deviation",
    "Direction",
    "FakeRiskScorer",
    "FakeTrendEnricher",
    "HistoryRecord",
    "MetricBaseline",
    "RiskAssessment",
    "RiskScorer",
    "Severity",
    "Signal",
    "TrendEnricher",
    "WeekMetrics",
    "apply_recurrence_bonus",
    "assess_confidence",
    "assess_from_timeline",
    "assign_severity",
    "attribute",
    "build_baseline",
    "build_personal_baselines",
    "classify",
    "cohort_shift",
    "compute_recurrence_bonus",
    "compute_risk_index",
    "confirm_consecutive",
    "confirm_signals",
    "confirm_signals_threshold",
    "cusum_shift_week",
    "detect_week_flags",
    "effect_size",
    "find_baseline",
    "is_shared_confound",
    "is_significant",
    "leading_metric",
    "longest_consecutive_run",
    "next_healthy_streak",
    "remove_shared_confound",
    "robust_z",
    "score_range",
    "suppresses_briefing",
]
