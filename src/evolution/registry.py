# src/evolution/registry.py
# Versioned model registry with a promotion gate (spec 6.2).
#
# "A versioned model registry, scheduled retraining on accumulated history plus
#  manager feedback, held-out evaluation before promotion, and automatic
#  rollback if the new version regresses. Every prediction records which model
#  version produced it."
#
# The shape of this is deliberately unexciting: a directory of JSON manifests
# and a pointer file naming the active version. No pickles, no framework, no
# service. What matters is not the storage, it is that ONE code path can change
# which model is pointed at people, and that path refuses unless the candidate
# has been evaluated on data it did not see and did not get worse.
#
# The gate is asymmetric, and that asymmetry is the point (see
# `domain.feedback.is_regression`): precision has to hold or improve, but any
# increase in harm blocks promotion outright. A model that finds more true
# positives by writing briefings that hurt people more often has not improved at
# this job -- it has moved its cost onto someone who cannot see the leaderboard.
#
# Rollback is automatic and requires no human in the loop, because the failure
# it guards against is exactly the one nobody is watching for at 3am.

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from src.config import get_settings
from src.domain.feedback import CalibrationReport, is_regression

logger = logging.getLogger(__name__)


#: Resolved per call, never captured at import -- see src/config.py.
def default_registry_dir() -> str:
    return get_settings().model_registry_dir


_ACTIVE_POINTER = "ACTIVE.json"

#: Version recorded when a prediction came from something other than a
#: registered model -- today, the LLM. Never left implicit: a prediction whose
#: origin is unknown cannot be attributed, and cannot be rolled back.
LLM_VERSION = "llm-gemini-2.5-flash"

#: Held-out evaluations smaller than this cannot support a promotion decision.
MIN_HOLDOUT_SIZE = 10


class ModelVersion(BaseModel):
    """One registered scoring model and the evidence for trusting it."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    version: str
    created_at: str
    #: What it was trained on. Recorded so a bad model can be traced back to the
    #: data that produced it rather than guessed at.
    trained_on_weeks: int = Field(default=0, ge=0)
    trained_on_feedback: int = Field(default=0, ge=0)
    #: Held-out evaluation result. None means never evaluated -- which is a
    #: permanent bar to promotion, not a formality to be waived under pressure.
    holdout: CalibrationReport | None = None
    holdout_size: int = Field(default=0, ge=0)
    notes: str = ""

    @property
    def is_promotable(self) -> bool:
        return self.holdout is not None and self.holdout_size >= MIN_HOLDOUT_SIZE


class PromotionResult(BaseModel):
    """The outcome of trying to promote a candidate, and why."""

    model_config = ConfigDict(frozen=True)

    promoted: bool
    version: str
    previous_version: str | None = None
    reason: str = ""


class ModelRegistry:
    """A directory of model manifests plus a pointer to the active one."""

    def __init__(self, directory: str | None = None) -> None:
        self.directory = directory or default_registry_dir()

    # -- storage ---------------------------------------------------------
    def _path(self, version: str) -> str:
        safe = version.replace(os.sep, "_").replace("/", "_")
        return os.path.join(self.directory, f"{safe}.json")

    def _pointer_path(self) -> str:
        return os.path.join(self.directory, _ACTIVE_POINTER)

    def register(self, version: ModelVersion) -> ModelVersion:
        """Record a model. Registering never makes it active."""
        os.makedirs(self.directory, exist_ok=True)
        with open(self._path(version.version), "w", encoding="utf-8") as fh:
            json.dump(version.model_dump(mode="json"), fh, indent=2)
        return version

    def get(self, version: str) -> ModelVersion | None:
        path = self._path(version)
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as fh:
                return ModelVersion.model_validate(json.load(fh))
        except Exception:
            logger.error("Unreadable model manifest.", exc_info=True)
            return None

    def versions(self) -> list[ModelVersion]:
        """Every registered version, newest first."""
        if not os.path.isdir(self.directory):
            return []
        found: list[ModelVersion] = []
        for name in sorted(os.listdir(self.directory)):
            if not name.endswith(".json") or name == _ACTIVE_POINTER:
                continue
            try:
                with open(os.path.join(self.directory, name), encoding="utf-8") as fh:
                    found.append(ModelVersion.model_validate(json.load(fh)))
            except Exception:
                logger.warning("Skipping unreadable manifest: %s", name)
        return sorted(found, key=lambda v: v.created_at, reverse=True)

    # -- the active pointer ----------------------------------------------
    def active_version(self) -> str:
        """The version currently making predictions.

        Falls back to the LLM marker rather than to a registered model: if the
        pointer is missing or unreadable, the honest answer is "not a registered
        model", never a guess at which one it might have been.
        """
        path = self._pointer_path()
        if not os.path.exists(path):
            return LLM_VERSION
        try:
            with open(path, encoding="utf-8") as fh:
                return str(json.load(fh).get("version") or LLM_VERSION)
        except Exception:
            logger.error("Unreadable active-model pointer.", exc_info=True)
            return LLM_VERSION

    def _set_active(self, version: str, *, reason: str) -> None:
        os.makedirs(self.directory, exist_ok=True)
        with open(self._pointer_path(), "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "version": version,
                    "activated_at": datetime.now(UTC).isoformat(),
                    "reason": reason,
                },
                fh,
                indent=2,
            )

    # -- the gate --------------------------------------------------------
    def promote(self, candidate_version: str) -> PromotionResult:
        """Make a candidate active, if and only if it has earned it.

        Four ways to be refused, each corresponding to a way a worse model could
        otherwise reach real people:
          * not registered      -- nothing to reason about
          * never evaluated     -- no evidence at all
          * evaluated too thin  -- evidence too small to distinguish from luck
          * regressed           -- evidence, and it says no
        """
        candidate = self.get(candidate_version)
        if candidate is None:
            return PromotionResult(
                promoted=False,
                version=candidate_version,
                reason="not registered",
            )

        if candidate.holdout is None:
            return PromotionResult(
                promoted=False,
                version=candidate_version,
                reason="no held-out evaluation -- never promote an unevaluated model",
            )

        if candidate.holdout_size < MIN_HOLDOUT_SIZE:
            return PromotionResult(
                promoted=False,
                version=candidate_version,
                reason=(
                    f"held-out set too small ({candidate.holdout_size} < "
                    f"{MIN_HOLDOUT_SIZE}) to support a promotion decision"
                ),
            )

        current_version = self.active_version()
        incumbent = self.get(current_version)

        if incumbent is not None and incumbent.holdout is not None:
            if is_regression(candidate.holdout, incumbent.holdout):
                return PromotionResult(
                    promoted=False,
                    version=candidate_version,
                    previous_version=current_version,
                    reason=(
                        "regression against the active model: precision fell or "
                        "harm rose"
                    ),
                )

        self._set_active(candidate_version, reason="promoted after held-out evaluation")
        return PromotionResult(
            promoted=True,
            version=candidate_version,
            previous_version=current_version,
            reason="held-out evaluation held or improved on the active model",
        )

    def rollback(self, *, reason: str) -> PromotionResult:
        """Return to the best previously-evaluated version.

        "Best" is the most recent version that both passed evaluation and is not
        the one currently active. If there is none, the pointer goes back to the
        LLM path -- a known-imperfect fallback beats a model that has just been
        observed to be harming people.
        """
        current = self.active_version()
        candidates = [
            version
            for version in self.versions()
            if version.version != current and version.is_promotable
        ]

        target = candidates[0].version if candidates else LLM_VERSION
        self._set_active(target, reason=f"rollback: {reason}")
        return PromotionResult(
            promoted=True,
            version=target,
            previous_version=current,
            reason=f"rolled back ({reason})",
        )

    def rollback_if_regressed(self, live: CalibrationReport) -> PromotionResult | None:
        """Automatic rollback when the live system drifts below its own evidence.

        Compares what the active model promised on its held-out set with what it
        is actually doing in production. Returns None when there is nothing to
        act on -- no active registered model, or not enough live feedback for the
        comparison to mean anything.
        """
        if not live.is_actionable:
            return None

        current = self.get(self.active_version())
        if current is None or current.holdout is None:
            return None

        if is_regression(live, current.holdout):
            return self.rollback(reason="live calibration regressed against held-out")
        return None
