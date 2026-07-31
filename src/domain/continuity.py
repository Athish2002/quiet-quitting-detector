# src/domain/continuity.py
# Memory that compounds (PRODUCTION_EVOLUTION_PROMPT.md 6.2).
#
# "Per-employee memory should carry forward: what was tried, what the manager
#  reported back, what changed after. Week 8's briefing must reference and build
#  on the week 3 intervention and its outcome -- not restart from zero."
#
# The failure this fixes is one managers feel immediately. Today every week's
# briefing is written as though it were the first: the same suggestion to
# schedule a 1-on-1, in week 3 and again in week 8, with no acknowledgement that
# the manager did exactly that in week 3 and reported it went badly. A tool that
# cannot remember what it already advised is a tool that wastes the time of the
# person trying to help, and the second identical suggestion is what teaches
# them to stop reading.
#
# What is carried forward is strictly behavioural (CONTEXT.md rule 5): scores,
# classifications, which signals were present, and the manager's structured
# verdict from src/domain/feedback.py. Never free text about a person, never
# anything about their health, never a characterisation of who they are.

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.domain.feedback import FeedbackReason, FeedbackRecord, FeedbackVerdict
from src.domain.models import HistoryRecord

#: How far back continuity looks. Long enough to span a quarter, short enough
#: that something from a year ago cannot follow somebody around.
CONTINUITY_WINDOW_WEEKS = 12

#: A drop of at least this many score points counts as a real improvement rather
#: than the number wobbling.
MEANINGFUL_IMPROVEMENT = 2


class WeeklyOutcome(BaseModel):
    """One prior week, reduced to what the next briefing needs to know."""

    model_config = ConfigDict(frozen=True)

    week: int = Field(ge=1)
    score: int = Field(ge=1, le=10)
    classification: str
    signal_names: tuple[str, ...] = ()
    manager_verdict: FeedbackVerdict | None = None
    manager_reason: FeedbackReason | None = None


class ContinuityNote(BaseModel):
    """The thread connecting this week's briefing to what came before.

    `summary` is written to be pasted into a prompt or shown to a manager as-is.
    """

    model_config = ConfigDict(frozen=True)

    has_history: bool = False
    weeks_covered: tuple[int, ...] = ()
    first_flagged_week: int | None = None
    #: Weeks the manager told us we were wrong. The single most important thing
    #: to carry forward: repeating a call a manager has already rejected, with no
    #: acknowledgement, is how a tool loses the person using it.
    disputed_weeks: tuple[int, ...] = ()
    #: Weeks the manager reported the briefing did harm.
    harmful_weeks: tuple[int, ...] = ()
    improving: bool = False
    worsening: bool = False
    recurring: bool = False
    persistent_signals: tuple[str, ...] = ()
    summary: str = ""

    @property
    def previously_disputed(self) -> bool:
        return bool(self.disputed_weeks or self.harmful_weeks)


def _signal_names(record: HistoryRecord | WeeklyOutcome) -> tuple[str, ...]:
    return tuple(getattr(record, "signal_names", ()) or ())


def build_outcomes(
    history: list[HistoryRecord],
    signals_by_week: dict[int, list[str]] | None = None,
    feedback: list[FeedbackRecord] | None = None,
) -> list[WeeklyOutcome]:
    """Fold stored evaluations and manager verdicts into one timeline.

    `history` is chronological. Weeks are numbered from the start of the window,
    since HistoryRecord does not carry its own week number.
    """
    by_week = {f.week: f for f in (feedback or [])}
    outcomes: list[WeeklyOutcome] = []

    for index, record in enumerate(history, start=1):
        verdict = by_week.get(index)
        outcomes.append(
            WeeklyOutcome(
                week=index,
                score=record.score,
                classification=record.classification,
                signal_names=tuple((signals_by_week or {}).get(index, ())),
                manager_verdict=verdict.verdict if verdict else None,
                manager_reason=verdict.reason if verdict else None,
            )
        )

    return outcomes[-CONTINUITY_WINDOW_WEEKS:]


def build_continuity(outcomes: list[WeeklyOutcome]) -> ContinuityNote:
    """Turn a person's prior weeks into the thread this week should build on."""
    if not outcomes:
        return ContinuityNote(summary="No prior weeks on record for this person.")

    ordered = sorted(outcomes, key=lambda o: o.week)
    elevated = [o for o in ordered if o.classification.strip().casefold() != "healthy"]

    disputed = tuple(
        o.week for o in ordered if o.manager_verdict is FeedbackVerdict.NOT_ACCURATE
    )
    harmful = tuple(
        o.week for o in ordered if o.manager_verdict is FeedbackVerdict.HARMFUL
    )

    first_flagged = elevated[0].week if elevated else None

    # Trend across the window, not week to week: a single week's wobble is not
    # a recovery and must not be reported to a manager as one.
    improving = worsening = False
    if len(ordered) >= 2:
        delta = ordered[-1].score - ordered[0].score
        improving = delta <= -MEANINGFUL_IMPROVEMENT
        worsening = delta >= MEANINGFUL_IMPROVEMENT

    # Elevated, then healthy, then elevated again -- the pattern a week-by-week
    # briefing is structurally incapable of noticing.
    recurring = False
    seen_elevated = seen_recovery = False
    for outcome in ordered:
        is_elevated = outcome.classification.strip().casefold() != "healthy"
        if is_elevated and seen_recovery:
            recurring = True
            break
        if is_elevated:
            seen_elevated = True
        elif seen_elevated:
            seen_recovery = True

    counts: dict[str, int] = {}
    for outcome in ordered:
        for name in _signal_names(outcome):
            counts[name] = counts.get(name, 0) + 1
    persistent = tuple(sorted(name for name, count in counts.items() if count >= 2))

    return ContinuityNote(
        has_history=True,
        weeks_covered=tuple(o.week for o in ordered),
        first_flagged_week=first_flagged,
        disputed_weeks=disputed,
        harmful_weeks=harmful,
        improving=improving,
        worsening=worsening,
        recurring=recurring,
        persistent_signals=persistent,
        summary=summarise(ordered, disputed, harmful, improving, worsening, recurring),
    )


def summarise(
    ordered: list[WeeklyOutcome],
    disputed: tuple[int, ...],
    harmful: tuple[int, ...],
    improving: bool,
    worsening: bool,
    recurring: bool,
) -> str:
    """Plain-language continuity, safe to place in a prompt or show a manager.

    Contains only week numbers, scores, classifications and signal names. No
    name, no free text, nothing about a person's circumstances.
    """
    parts: list[str] = [
        f"Prior weeks on record: {len(ordered)} "
        f"(weeks {ordered[0].week}-{ordered[-1].week})."
    ]

    first_elevated = next(
        (o for o in ordered if o.classification.strip().casefold() != "healthy"), None
    )
    if first_elevated:
        parts.append(
            f"First raised in week {first_elevated.week} as "
            f"{first_elevated.classification} ({first_elevated.score}/10)."
        )
    else:
        parts.append("Never previously raised above Healthy.")

    if harmful:
        parts.append(
            f"IMPORTANT: the manager reported the week "
            f"{', '.join(str(w) for w in harmful)} briefing as harmful. Do not "
            "repeat that framing. Lead with the manager's own knowledge of the "
            "situation rather than with the metrics."
        )
    elif disputed:
        parts.append(
            f"The manager marked the week {', '.join(str(w) for w in disputed)} "
            "briefing as not accurate. Acknowledge that explicitly and treat this "
            "week's signals as a question rather than a finding."
        )

    if recurring:
        parts.append(
            "This has been raised, resolved, and raised again -- treat it as a "
            "recurring pattern rather than a new development."
        )
    elif improving:
        parts.append(
            "Scores have moved down materially across the window. Whatever the "
            "manager has been doing appears to be working; the useful briefing "
            "reinforces it rather than restarting the conversation."
        )
    elif worsening:
        parts.append(
            "Scores have moved up materially across the window despite the "
            "earlier briefing, so the previous approach has not helped."
        )

    return " ".join(parts)
