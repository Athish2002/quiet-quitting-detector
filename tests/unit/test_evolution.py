# Phase 3 -- agent evolution (PRODUCTION_EVOLUTION_PROMPT.md 6.2).
#
# Covers manager feedback, calibration, the model registry's promotion gate,
# compounding memory, and the self-critique pass.
#
# The tests are written around what these components are FOR. "compute_calibration
# returns 0.5" proves arithmetic; "a model that increases harm cannot be promoted
# however much its precision improved" is the property that decides whether this
# system is safe to point at people.

import pytest

from src.domain.continuity import (
    WeeklyOutcome,
    build_continuity,
    build_outcomes,
)
from src.domain.critique import Finding, critique_briefing
from src.domain.feedback import (
    MAX_ACCEPTABLE_HARM_RATE,
    MIN_FEEDBACK_FOR_CALIBRATION,
    CalibrationReport,
    FeedbackReason,
    FeedbackRecord,
    FeedbackVerdict,
    compute_calibration,
    is_regression,
    needs_review,
)
from src.domain.models import Confidence, HistoryRecord
from src.evolution.calibration import CalibrationTracker
from src.evolution.feedback_store import FeedbackStore
from src.evolution.registry import (
    LLM_VERSION,
    MIN_HOLDOUT_SIZE,
    ModelRegistry,
    ModelVersion,
)


def _feedback(
    week=1,
    verdict=FeedbackVerdict.ACCURATE,
    classification="At Risk",
    reason=FeedbackReason.NOT_STATED,
    subject="priya",
    version="v1",
):
    return FeedbackRecord(
        subject_id=subject,
        week=week,
        predicted_score=7,
        predicted_classification=classification,
        verdict=verdict,
        reason=reason,
        model_version=version,
    )


# ---------------------------------------------------------------------------
# Feedback and calibration
# ---------------------------------------------------------------------------
def test_calibration_of_nothing_is_not_a_score():
    """No feedback means we do not know, not that we are at 0%."""
    empty = compute_calibration([])
    assert empty.total == 0
    assert empty.elevated_precision is None
    assert empty.is_actionable is False


def test_harm_is_tracked_separately_from_accuracy():
    """A tool that is 90% accurate and harmful 10% of the time is not a good tool.

    Collapsing these into one number would let the system's headline metric
    improve while the harm it caused went up.
    """
    records = [_feedback(week=w) for w in range(1, 10)]
    records.append(_feedback(week=10, verdict=FeedbackVerdict.HARMFUL))

    report = compute_calibration(records)
    assert report.accurate == 9
    assert report.harmful == 1
    assert report.harm_rate == pytest.approx(0.1)
    # Harm is not netted off against the accuracy figure.
    assert report.elevated_precision == pytest.approx(0.9)


def test_precision_is_measured_on_elevated_calls_only():
    """Nobody is harmed by an unnoticed 'Healthy'. Precision on the calls that
    carry consequences is the number that matters."""
    records = [
        _feedback(week=1, classification="At Risk", verdict=FeedbackVerdict.ACCURATE),
        _feedback(
            week=2, classification="At Risk", verdict=FeedbackVerdict.NOT_ACCURATE
        ),
        _feedback(
            week=3, classification="Healthy", verdict=FeedbackVerdict.NOT_ACCURATE
        ),
    ]
    report = compute_calibration(records)
    assert report.elevated_precision == pytest.approx(0.5)


def test_system_fault_is_separated_from_the_world_being_complicated():
    """'We flagged someone on approved leave' and 'we were right but it did not
    help' need completely different fixes."""
    records = [
        _feedback(
            week=1,
            verdict=FeedbackVerdict.NOT_ACCURATE,
            reason=FeedbackReason.KNOWN_LEAVE,
        ),
        _feedback(
            week=2, verdict=FeedbackVerdict.NOT_ACCURATE, reason=FeedbackReason.TOO_LATE
        ),
    ]
    report = compute_calibration(records)
    assert report.system_fault_rate == pytest.approx(0.5)

    assert records[0].blames_the_system is True
    assert records[1].blames_the_system is False
    assert _feedback(verdict=FeedbackVerdict.ACCURATE).blames_the_system is False


def test_a_handful_of_verdicts_is_not_a_percentage():
    """Three managers disagreeing is a conversation, not a 33% accuracy rate."""
    few = compute_calibration([_feedback(week=w) for w in range(1, 4)])
    assert few.is_actionable is False
    assert needs_review(few) is False

    many = compute_calibration(
        [_feedback(week=w) for w in range(1, MIN_FEEDBACK_FOR_CALIBRATION + 1)]
    )
    assert many.is_actionable is True


def test_review_is_triggered_by_harm_or_by_crying_wolf():
    harmful = compute_calibration(
        [_feedback(week=w, verdict=FeedbackVerdict.HARMFUL) for w in range(1, 4)]
        + [_feedback(week=w) for w in range(4, 15)]
    )
    assert harmful.harm_rate > MAX_ACCEPTABLE_HARM_RATE
    assert needs_review(harmful) is True

    crying_wolf = compute_calibration(
        [_feedback(week=w, verdict=FeedbackVerdict.NOT_ACCURATE) for w in range(1, 9)]
        + [_feedback(week=w) for w in range(9, 15)]
    )
    assert needs_review(crying_wolf) is True

    good = compute_calibration([_feedback(week=w) for w in range(1, 15)])
    assert needs_review(good) is False


def test_more_harm_blocks_promotion_however_much_precision_improved():
    """The asymmetry that keeps this a wellbeing tool.

    A model that finds more true positives by writing briefings that hurt people
    more often has not got better at this job -- it has moved its cost onto
    someone who cannot see the leaderboard.
    """
    incumbent = CalibrationReport(total=50, elevated_precision=0.70, harm_rate=0.01)
    more_accurate_but_harmful = CalibrationReport(
        total=50, elevated_precision=0.95, harm_rate=0.02
    )
    assert is_regression(more_accurate_but_harmful, incumbent) is True

    genuinely_better = CalibrationReport(
        total=50, elevated_precision=0.80, harm_rate=0.01
    )
    assert is_regression(genuinely_better, incumbent) is False

    less_accurate = CalibrationReport(total=50, elevated_precision=0.60, harm_rate=0.01)
    assert is_regression(less_accurate, incumbent) is True

    # Missing precision on either side is not evidence of regression.
    unknown = CalibrationReport(total=50, elevated_precision=None, harm_rate=0.01)
    assert is_regression(unknown, incumbent) is False


# ---------------------------------------------------------------------------
# Feedback store
# ---------------------------------------------------------------------------
def test_a_manager_changing_their_mind_replaces_their_verdict(tmp_path):
    """Not appends. Otherwise calibration weights whoever clicked most."""
    store = FeedbackStore(str(tmp_path / "fb.db"))
    store.record(_feedback(week=3, verdict=FeedbackVerdict.ACCURATE))
    store.record(_feedback(week=3, verdict=FeedbackVerdict.NOT_ACCURATE))

    stored = store.all()
    assert len(stored) == 1
    assert stored[0].verdict is FeedbackVerdict.NOT_ACCURATE
    assert store.count() == 1


def test_feedback_store_has_nowhere_to_put_free_text(tmp_path):
    """CONTEXT.md rule 5, enforced by the schema rather than by asking nicely."""
    store = FeedbackStore(str(tmp_path / "fb.db"))
    store.record(_feedback())

    import sqlite3

    conn = sqlite3.connect(str(tmp_path / "fb.db"))
    columns = {row[1] for row in conn.execute("PRAGMA table_info(manager_feedback)")}
    conn.close()

    for banned in ("note", "notes", "comment", "comments", "detail", "details", "text"):
        assert banned not in columns, f"free-text column {banned!r} added to feedback"


def test_feedback_can_be_filtered_by_subject_and_version(tmp_path):
    store = FeedbackStore(str(tmp_path / "fb.db"))
    store.record(_feedback(week=1, subject="priya", version="v1"))
    store.record(_feedback(week=2, subject="ade", version="v2"))

    assert len(store.for_subject("priya")) == 1
    assert len(store.all(model_version="v2")) == 1
    assert len(store.all()) == 2


def test_one_unreadable_row_does_not_take_down_calibration(tmp_path):
    """The calibration view is what would tell an operator something is wrong.
    It must not be the thing that breaks first."""
    db = tmp_path / "fb.db"
    store = FeedbackStore(str(db))
    store.record(_feedback(week=1))

    import sqlite3

    conn = sqlite3.connect(str(db))
    conn.execute("UPDATE manager_feedback SET verdict = 'nonsense-from-the-future'")
    conn.commit()
    conn.close()

    records = store.all()
    assert len(records) == 1
    assert records[0].verdict is FeedbackVerdict.NOT_ACCURATE


def test_calibration_tracker_reports_drift(tmp_path):
    store = FeedbackStore(str(tmp_path / "fb.db"))
    for week in range(1, 21):
        store.record(_feedback(week=week, verdict=FeedbackVerdict.ACCURATE))
    for week in range(21, 41):
        store.record(_feedback(week=week, verdict=FeedbackVerdict.NOT_ACCURATE))

    view = CalibrationTracker(store).drift(active_model_version="v1")
    assert view.overall.total == 40
    assert view.drifting is True
    assert view.review_required is True
    assert "drift" in view.message.lower()


def test_calibration_says_so_when_it_cannot_tell(tmp_path):
    store = FeedbackStore(str(tmp_path / "fb.db"))
    store.record(_feedback(week=1))

    view = CalibrationTracker(store).drift()
    assert view.drifting is False
    assert "not enough" in view.message.lower()
    assert "unvalidated" in view.message.lower()


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------
def _version(
    name, *, precision=0.8, harm=0.0, holdout=MIN_HOLDOUT_SIZE, evaluated=True
):
    return ModelVersion(
        version=name,
        created_at=f"2026-01-{int(name[-1]) + 1:02d}T00:00:00Z",
        trained_on_weeks=100,
        trained_on_feedback=50,
        holdout=(
            CalibrationReport(
                total=holdout, elevated_precision=precision, harm_rate=harm
            )
            if evaluated
            else None
        ),
        holdout_size=holdout,
    )


def test_an_unevaluated_model_can_never_be_promoted(tmp_path):
    registry = ModelRegistry(str(tmp_path))
    registry.register(_version("v1", evaluated=False))

    result = registry.promote("v1")
    assert result.promoted is False
    assert "no held-out evaluation" in result.reason
    assert registry.active_version() == LLM_VERSION


def test_a_model_evaluated_on_too_little_data_cannot_be_promoted(tmp_path):
    registry = ModelRegistry(str(tmp_path))
    registry.register(_version("v1", holdout=MIN_HOLDOUT_SIZE - 1))

    result = registry.promote("v1")
    assert result.promoted is False
    assert "too small" in result.reason


def test_an_unregistered_model_cannot_be_promoted(tmp_path):
    result = ModelRegistry(str(tmp_path)).promote("does-not-exist")
    assert result.promoted is False
    assert result.reason == "not registered"


def test_a_properly_evaluated_model_is_promoted(tmp_path):
    registry = ModelRegistry(str(tmp_path))
    registry.register(_version("v1"))

    result = registry.promote("v1")
    assert result.promoted is True
    assert registry.active_version() == "v1"


def test_a_regressed_candidate_is_refused(tmp_path):
    registry = ModelRegistry(str(tmp_path))
    registry.register(_version("v1", precision=0.85, harm=0.0))
    registry.promote("v1")

    registry.register(_version("v2", precision=0.60, harm=0.0))
    result = registry.promote("v2")

    assert result.promoted is False
    assert "regression" in result.reason
    assert registry.active_version() == "v1", "a worse model reached production"


def test_rollback_returns_to_the_best_evaluated_version(tmp_path):
    registry = ModelRegistry(str(tmp_path))
    registry.register(_version("v1", precision=0.85))
    registry.promote("v1")
    registry.register(_version("v2", precision=0.90))
    registry.promote("v2")
    assert registry.active_version() == "v2"

    result = registry.rollback(reason="harm spike")
    assert result.promoted is True
    assert registry.active_version() == "v1"
    assert "harm spike" in result.reason


def test_rollback_with_nowhere_to_go_falls_back_to_the_llm(tmp_path):
    """A known-imperfect fallback beats a model observed to be harming people."""
    registry = ModelRegistry(str(tmp_path))
    registry.register(_version("v1"))
    registry.promote("v1")

    registry.rollback(reason="nothing else registered")
    assert registry.active_version() == LLM_VERSION


def test_automatic_rollback_when_live_performance_regresses(tmp_path):
    registry = ModelRegistry(str(tmp_path))
    registry.register(_version("v1", precision=0.90, harm=0.0))
    registry.register(_version("v2", precision=0.92, harm=0.0))
    registry.promote("v1")
    registry.promote("v2")
    assert registry.active_version() == "v2"

    live = CalibrationReport(total=40, elevated_precision=0.40, harm_rate=0.10)
    result = registry.rollback_if_regressed(live)

    assert result is not None
    assert registry.active_version() == "v1"


def test_automatic_rollback_holds_off_without_enough_evidence(tmp_path):
    registry = ModelRegistry(str(tmp_path))
    registry.register(_version("v1"))
    registry.promote("v1")

    thin = CalibrationReport(total=2, elevated_precision=0.0, harm_rate=1.0)
    assert registry.rollback_if_regressed(thin) is None
    assert registry.active_version() == "v1"


def test_registry_survives_an_unreadable_manifest(tmp_path):
    registry = ModelRegistry(str(tmp_path))
    registry.register(_version("v1"))
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")

    versions = registry.versions()
    assert [v.version for v in versions] == ["v1"]
    assert registry.get("broken") is None


# ---------------------------------------------------------------------------
# Compounding memory
# ---------------------------------------------------------------------------
def test_no_history_says_so_rather_than_inventing_continuity():
    note = build_continuity([])
    assert note.has_history is False
    assert "No prior weeks" in note.summary


def test_week_eight_references_the_week_three_intervention():
    """The documented case study required by the Phase 3 exit criterion.

    A manager was briefed in week 3, marked that briefing as not accurate, and
    the situation has since worsened. Week 8's briefing must carry all of that.
    Without it, week 8 repeats week 3's suggestion verbatim to a manager who
    already tried it and told us it was wrong -- which is how a tool teaches the
    person using it to stop reading.
    """
    history = [
        HistoryRecord(score=2, classification="Healthy"),
        HistoryRecord(score=3, classification="Healthy"),
        HistoryRecord(score=6, classification="At Risk"),
        HistoryRecord(score=5, classification="Watch"),
        HistoryRecord(score=4, classification="Watch"),
        HistoryRecord(score=6, classification="At Risk"),
        HistoryRecord(score=7, classification="At Risk"),
    ]
    signals_by_week = {
        3: ["Declining Task Completion"],
        6: ["Declining Task Completion"],
        7: ["Declining Task Completion", "Response Time Spike"],
    }
    feedback = [
        FeedbackRecord(
            subject_id="priya",
            week=3,
            predicted_score=6,
            predicted_classification="At Risk",
            verdict=FeedbackVerdict.NOT_ACCURATE,
            reason=FeedbackReason.TEAM_EVENT,
        )
    ]

    note = build_continuity(build_outcomes(history, signals_by_week, feedback))

    assert note.has_history is True
    assert note.first_flagged_week == 3
    assert note.disputed_weeks == (3,)
    assert note.previously_disputed is True
    assert note.worsening is True
    assert "Declining Task Completion" in note.persistent_signals

    # The summary is what actually reaches the briefing prompt.
    assert "week 3" in note.summary
    assert "not accurate" in note.summary.lower()
    assert "question rather than a finding" in note.summary


def test_a_harmful_briefing_changes_how_the_next_one_is_written():
    outcomes = [
        WeeklyOutcome(week=1, score=6, classification="At Risk"),
        WeeklyOutcome(
            week=2,
            score=7,
            classification="At Risk",
            manager_verdict=FeedbackVerdict.HARMFUL,
        ),
    ]
    note = build_continuity(outcomes)
    assert note.harmful_weeks == (2,)
    assert "harmful" in note.summary.lower()
    assert "do not repeat that framing" in note.summary.lower()


def test_recovery_is_recognised_rather_than_restarted():
    outcomes = [
        WeeklyOutcome(week=1, score=8, classification="Silent Exit"),
        WeeklyOutcome(week=2, score=6, classification="At Risk"),
        WeeklyOutcome(week=3, score=3, classification="Healthy"),
    ]
    note = build_continuity(outcomes)
    assert note.improving is True
    assert note.worsening is False
    assert "appears to be working" in note.summary


def test_a_recurring_pattern_is_named_as_recurring():
    outcomes = [
        WeeklyOutcome(week=1, score=6, classification="At Risk"),
        WeeklyOutcome(week=2, score=2, classification="Healthy"),
        WeeklyOutcome(week=3, score=2, classification="Healthy"),
        WeeklyOutcome(week=4, score=6, classification="At Risk"),
    ]
    note = build_continuity(outcomes)
    assert note.recurring is True
    assert "raised again" in note.summary


def test_continuity_carries_no_free_text_about_a_person():
    """CONTEXT.md rule 5. Week numbers, scores, classifications, signal names."""
    outcomes = [
        WeeklyOutcome(
            week=1,
            score=7,
            classification="At Risk",
            signal_names=("Declining Task Completion",),
            manager_verdict=FeedbackVerdict.NOT_ACCURATE,
            manager_reason=FeedbackReason.KNOWN_LEAVE,
        )
    ]
    summary = build_continuity(outcomes).summary.lower()
    for forbidden in ("leave", "sick", "health", "family", "personal", "attitude"):
        assert forbidden not in summary, f"continuity summary leaked {forbidden!r}"


# ---------------------------------------------------------------------------
# Self-critique
# ---------------------------------------------------------------------------
def test_critic_blocks_a_verdict_on_someone_s_inner_state():
    """Contains no banned word, so the regex validator passes it."""
    critique = critique_briefing(
        "Priya has clearly become disengaged and no longer cares about the work.",
        first_name="Priya",
        confirmed_signals=["Declining Task Completion"],
    )
    assert Finding.MIND_READING in critique.findings
    assert critique.must_block is True


def test_critic_blocks_health_content_and_surname_leaks():
    health = critique_briefing(
        "Task completion is down, possibly due to a recent illness.",
        first_name="Ade",
        confirmed_signals=["Declining Task Completion"],
    )
    assert Finding.PROHIBITED_TOPIC in health.findings
    assert health.must_block is True

    leak = critique_briefing(
        "Priya Raman has completed fewer tasks than usual.",
        first_name="Priya",
        confirmed_signals=["Declining Task Completion"],
    )
    assert Finding.IDENTITY_LEAK in leak.findings
    assert leak.must_block is True


def test_critic_catches_a_signal_the_detector_never_confirmed():
    """A model asked for supportive advice will helpfully invent a second
    problem, and the manager cannot tell which one was measured."""
    critique = critique_briefing(
        "Task completion has fallen and response times have risen sharply.",
        first_name="Ade",
        confirmed_signals=["Declining Task Completion"],
    )
    assert Finding.UNSUPPORTED_BY_EVIDENCE in critique.findings


def test_critic_requires_the_caveat_when_confidence_is_low():
    bald = critique_briefing(
        "Task completion has fallen. Schedule a 1-on-1 this week.",
        first_name="Ade",
        confirmed_signals=["Declining Task Completion"],
        confidence=Confidence.LOW,
    )
    assert Finding.MISSING_UNCERTAINTY_CAVEAT in bald.findings

    hedged = critique_briefing(
        "Task completion may have fallen; it could be worth checking in.",
        first_name="Ade",
        confirmed_signals=["Declining Task Completion"],
        confidence=Confidence.LOW,
    )
    assert Finding.MISSING_UNCERTAINTY_CAVEAT not in hedged.findings


def test_critic_requires_a_data_gap_to_be_noted():
    critique = critique_briefing(
        "Task completion has been lower than usual over recent weeks.",
        first_name="Ade",
        confirmed_signals=["Declining Task Completion"],
        has_data_gap=True,
    )
    assert Finding.MISSING_DATA_GAP_NOTE in critique.findings


def test_critic_rejects_empty_output():
    critique = critique_briefing("   ", first_name="Ade", confirmed_signals=[])
    assert critique.findings == (Finding.EMPTY,)
    assert critique.must_block is True


def test_critic_lets_a_good_briefing_through():
    """If the critic blocked everything, the safe fallback would replace every
    briefing and the system would say nothing at all."""
    critique = critique_briefing(
        "Signals Detected: task completion has been lower than Ade's own usual "
        "range for two weeks. It may be worth asking whether workload or "
        "blockers have changed. 3 Supportive Things to Say: 'How are you finding "
        "your workload?' 'Is anything getting in your way?' 'What would help?'",
        first_name="Ade",
        confirmed_signals=["Declining Task Completion"],
        confidence=Confidence.LOW,
    )
    assert critique.is_clean is True
    assert critique.must_block is False
    assert critique.revision_instructions() == ""


def test_critique_explains_itself_to_the_drafting_agent():
    critique = critique_briefing(
        "Ade has obviously checked out.",
        first_name="Ade",
        confirmed_signals=[],
    )
    instructions = critique.revision_instructions()
    assert instructions.startswith("Revise the briefing")
    assert "observed" in instructions
    assert "certainty" in instructions


def test_an_adverb_does_not_smuggle_a_verdict_past_the_critic():
    """A model writes 'has clearly become disengaged', not 'is disengaged'.

    The hedged, professional-sounding phrasing is the one a manager is most
    likely to believe, so it must not be the one that gets through.
    """
    for phrasing in (
        "Ade is disengaged.",
        "Ade has clearly become disengaged.",
        "Ade seems increasingly unmotivated.",
        "Ade has obviously checked out.",
        "Ade appears somewhat withdrawn.",
        "Ade has lost all enthusiasm.",
        "Ade no longer seems interested.",
    ):
        critique = critique_briefing(
            phrasing, first_name="Ade", confirmed_signals=["Declining Task Completion"]
        )
        assert Finding.MIND_READING in critique.findings, phrasing
        assert critique.must_block is True, phrasing


def test_ordinary_prose_after_a_first_name_is_not_a_surname():
    """Broad name detection would fire constantly and train everyone to ignore it."""
    critique = critique_briefing(
        "Ade has completed fewer tasks. Ade may need support. Ade The work is steady.",
        first_name="Ade",
        confirmed_signals=["Declining Task Completion"],
    )
    assert Finding.IDENTITY_LEAK not in critique.findings
