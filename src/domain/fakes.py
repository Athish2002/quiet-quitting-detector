# src/domain/fakes.py
# Deterministic stand-ins for the LLM-backed agents.
#
# These live in `domain` rather than `tests/` on purpose: they are pure functions
# of their arguments with no I/O, they satisfy the same import contract as the
# rest of the package, and both entrypoints need to import them to prove parity
# (PRODUCTION_EVOLUTION_PROMPT.md Phase 1 exit criterion).
#
# They are not fixtures full of canned strings. `FakeRiskScorer` scores using the
# real deterministic index in `domain.risk`, so a parity run exercises genuine
# scoring logic -- only the nondeterminism is removed.

from __future__ import annotations

from src.domain.attribution import attribute, leading_metric
from src.domain.models import (
    Confidence,
    HistoryRecord,
    RiskAssessment,
    Signal,
    WeekMetrics,
)
from src.domain.risk import classify, compute_risk_index
from src.domain.uncertainty import assess_from_timeline, score_range


class FakeTrendEnricher:
    """Adds fixed, supportive prose. Never alters the evidence fields."""

    def enrich(self, first_name: str, signals: list[Signal]) -> list[Signal]:
        enriched: list[Signal] = []
        for signal in signals:
            weeks = ", ".join(str(w) for w in signal.weeks_detected)
            enriched.append(
                signal.model_copy(
                    update={
                        "details": (
                            f"{signal.signal_name} observed for {first_name} in "
                            f"week(s) {weeks} relative to their own baseline."
                        )
                    }
                )
            )
        return enriched


class FakeRiskScorer:
    """Scores from the deterministic risk index instead of a language model.

    Returns the PRE-recurrence score, matching what the LLM path returns, so the
    caller's recurrence/decay handling is identical either way.

    `insufficient_data` is set when there are no signals AND no history at all:
    that is not evidence of health, it is an absence of evidence, and the
    briefing has to say so (CONTEXT.md rule 3).
    """

    def score(
        self,
        first_name: str,
        signals: list[Signal],
        week_number: int,
        history: list[HistoryRecord],
        timeline: list[WeekMetrics] | None = None,
    ) -> RiskAssessment:
        score = compute_risk_index(signals)
        classification = classify(score)
        attributions = attribute(signals)

        confidence = assess_from_timeline(timeline) if timeline else Confidence.LOW

        scoring = [s for s in signals if not s.wellbeing_only]
        if scoring:
            named = ", ".join(sorted(s.signal_name for s in scoring))
            rationale = (
                f"Week {week_number}: {len(scoring)} confirmed pattern(s) "
                f"against {first_name}'s own baseline ({named})."
            )
            driver = leading_metric(attributions)
            if driver:
                rationale += f" Largest contributor: {driver}."
        else:
            rationale = (
                f"Week {week_number}: no pattern persisted for two or more "
                f"consecutive weeks against {first_name}'s own baseline."
            )

        # Low confidence is stated in the rationale, not just carried in a field
        # a consumer might not read. A number a manager acts on has to arrive
        # with its own caveat attached (6.1).
        if confidence in (Confidence.NONE, Confidence.LOW):
            rationale += (
                " Confidence is low -- there is not yet enough of "
                f"{first_name}'s own history for this to be more than a "
                "prompt to check in."
            )

        return RiskAssessment(
            score=score,
            classification=classification,
            rationale=rationale,
            insufficient_data=(
                confidence is Confidence.NONE or (not signals and not history)
            ),
            confidence=confidence,
            score_range=score_range(score, confidence),
            attributions=attributions,
        )
