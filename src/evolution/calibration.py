# src/evolution/calibration.py
# Is the system actually right? (spec 6.2)
#
# "Track over time whether 'At Risk' predictions correspond to manager-confirmed
#  reality. Surface drift on an internal metrics page. A system that quietly
#  becomes miscalibrated is worse than no system."
#
# Worse for a reason worth stating plainly: an uncalibrated tool nobody trusts
# gets ignored and does nothing, while an uncalibrated tool everybody trusts
# changes how managers treat their reports. The dangerous state is not being
# wrong -- it is being wrong and credible.
#
# All arithmetic lives in `domain.feedback`. This class is the part that reads a
# database and slices by time and version.

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from src.domain.feedback import (
    CalibrationReport,
    FeedbackRecord,
    compute_calibration,
    needs_review,
)
from src.evolution.feedback_store import FeedbackStore

#: Feedback newer than this forms the "recent" window used for drift detection.
#: Compared against everything before it, so a system that was accurate for six
#: months and has been wrong for three weeks shows up as drift rather than being
#: averaged into a still-comfortable lifetime figure.
RECENT_WINDOW = 30


class DriftView(BaseModel):
    """Lifetime vs recent calibration, and whether the gap needs attention."""

    model_config = ConfigDict(frozen=True)

    overall: CalibrationReport
    recent: CalibrationReport
    active_model_version: str = ""
    review_required: bool = False
    drifting: bool = False
    message: str = ""


class CalibrationTracker:
    """Reads stored feedback and reports whether the system is still calibrated."""

    def __init__(self, store: FeedbackStore | None = None) -> None:
        self.store = store or FeedbackStore()

    def report(self, *, model_version: str | None = None) -> CalibrationReport:
        return compute_calibration(self.store.all(model_version=model_version))

    def for_subject(self, subject_id: str) -> list[FeedbackRecord]:
        return self.store.for_subject(subject_id)

    def drift(self, *, active_model_version: str = "") -> DriftView:
        """Compare the recent window against everything before it."""
        records = self.store.all()
        overall = compute_calibration(records)
        recent_records = records[-RECENT_WINDOW:]
        recent = compute_calibration(recent_records)

        drifting = _has_drifted(overall, recent)
        review = needs_review(recent) or needs_review(overall)

        return DriftView(
            overall=overall,
            recent=recent,
            active_model_version=active_model_version,
            review_required=review,
            drifting=drifting,
            message=_describe(overall, recent, drifting, review),
        )


def _has_drifted(overall: CalibrationReport, recent: CalibrationReport) -> bool:
    """Whether recent performance has moved away from the lifetime picture."""
    if not recent.is_actionable or not overall.is_actionable:
        return False
    if recent.harm_rate > overall.harm_rate:
        return True
    if recent.elevated_precision is None or overall.elevated_precision is None:
        return False
    return recent.elevated_precision < overall.elevated_precision - 0.10


def _describe(
    overall: CalibrationReport,
    recent: CalibrationReport,
    drifting: bool,
    review: bool,
) -> str:
    """A sentence an operator can act on, or an honest statement that we cannot tell."""
    if not overall.is_actionable:
        return (
            f"Only {overall.total} manager verdict(s) recorded. Not enough to say "
            "whether this system is calibrated -- treat every score as unvalidated."
        )

    parts = []
    if overall.elevated_precision is not None:
        parts.append(
            f"Of the briefings raised above Healthy, managers confirmed "
            f"{overall.elevated_precision:.0%} over {overall.total} verdicts."
        )
    if overall.harmful:
        parts.append(
            f"{overall.harmful} briefing(s) were reported as harmful "
            f"({overall.harm_rate:.0%})."
        )
    if drifting:
        parts.append(
            "Recent performance is materially worse than the lifetime figure -- "
            "this is drift, not noise, and the cause should be found before the "
            "next scheduled retrain."
        )
    if review:
        parts.append(
            "REVIEW REQUIRED: the system is outside its acceptable operating "
            "range. Consider rolling back the active model."
        )
    return " ".join(parts)
