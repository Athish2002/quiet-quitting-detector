# src/evolution/ -- the parts of 6.2 that have to remember things.
#
# `src/domain/feedback.py`, `continuity.py` and `critique.py` hold the decisions:
# what counts as a regression, what a calibration figure means, whether a draft
# is safe to send. They are pure and property-tested.
#
# This package holds only the storage and orchestration those decisions need --
# SQLite tables, a model registry directory, the promote/rollback sequence. It
# may import from `domain`; `domain` may never import from here.
#
# The split matters for one specific reason: the rules about whether a model is
# good enough to be pointed at people must be testable without a database, a
# trained model, or a filesystem. Anything that needs infrastructure to verify
# tends to get verified less often.

from src.evolution.calibration import CalibrationTracker
from src.evolution.feedback_store import FeedbackStore
from src.evolution.registry import ModelRegistry, ModelVersion

__all__ = [
    "CalibrationTracker",
    "FeedbackStore",
    "ModelRegistry",
    "ModelVersion",
]
