# src/app_utils/local_ml.py
# A small, self-training local risk model used when the Gemini API is
# unavailable (quota exhaustion, network failure, invalid key).
#
# Unlike a fixed nearest-neighbor lookup, this trains a tiny scikit-learn
# regression model on this project's own accumulated data/memory/*.json
# records every time it is invoked, so the offline fallback gets smarter as
# more weeks of real evaluations accumulate. When there isn't yet enough
# historical data to train on, callers should degrade further to a
# similarity-based match (see risk_scorer_agent._nearest_neighbor_fallback).

import glob
import json
import logging
import os

logger = logging.getLogger(__name__)

# Below this many usable historical records, a regression fit is not
# meaningful -- the caller should fall back to nearest-neighbor matching.
MIN_TRAINING_SAMPLES = 6

_SEVERITY_WEIGHT = {"low": 1.0, "medium": 2.0, "high": 3.0}


def _signal_name(signal: dict) -> str | None:
    return signal.get("signal_name") or signal.get("signal")


def _load_training_corpus(memory_dir: str) -> list[dict]:
    """Load valid historical records, excluding the fallback's own past
    outputs so it never trains on (and reinforces) its own guesses."""
    corpus: list[dict] = []
    for file_path in glob.glob(os.path.join(memory_dir, "*.json")):
        try:
            with open(file_path, encoding="utf-8") as fh:
                record = json.load(fh)
        except Exception:
            continue

        rationale = record.get("rationale") or ""
        if "Fallback Model]" in rationale or "Local ML Fallback" in rationale:
            continue
        if "score" not in record:
            continue

        corpus.append(record)
    return corpus


def _signal_vocabulary(corpus: list[dict]) -> list[str]:
    names: set[str] = set()
    for record in corpus:
        for sig in record.get("signals", []):
            name = _signal_name(sig)
            if name and name != "MISSING_DATA_GAP":
                names.add(name)
    return sorted(names)


def _vectorize(signals: list[dict], vocab: list[str]) -> list[float]:
    """Multi-hot feature vector, weighted by severity, over the known
    signal vocabulary learned from the training corpus."""
    vec = []
    for name in vocab:
        matches = [s for s in signals if _signal_name(s) == name]
        if matches:
            severity = (matches[0].get("severity") or "medium").lower()
            vec.append(_SEVERITY_WEIGHT.get(severity, 2.0))
        else:
            vec.append(0.0)
    return vec


class LocalRiskModel:
    """A regression model trained on this project's own historical risk
    evaluations, predicting a numeric score from a signal feature vector."""

    def __init__(self, vocab: list[str], model, sample_count: int):
        self.vocab = vocab
        self.model = model
        self.sample_count = sample_count

    def predict_score(self, signals: list[dict]) -> float:
        vec = _vectorize(signals, self.vocab)
        return float(self.model.predict([vec])[0])


def train_local_model(memory_dir: str) -> LocalRiskModel | None:
    """Train (or decline to train) a local risk model from memory_dir.

    Returns None when there isn't enough usable, sufficiently varied
    historical data -- the caller should degrade further in that case.
    """
    corpus = _load_training_corpus(memory_dir)
    if len(corpus) < MIN_TRAINING_SAMPLES:
        return None

    vocab = _signal_vocabulary(corpus)
    if not vocab:
        return None

    features = [_vectorize(r.get("signals", []), vocab) for r in corpus]
    scores = [r.get("score", 4) for r in corpus]

    if len(set(scores)) < 2:
        # Every historical score is identical -- a regression fit would be
        # meaningless noise. Let the caller fall back further.
        return None

    try:
        from sklearn.linear_model import Ridge

        model = Ridge(alpha=1.0)
        model.fit(features, scores)
    except Exception:
        logger.warning("Local ML model training failed -- skipping.", exc_info=True)
        return None

    return LocalRiskModel(vocab, model, sample_count=len(corpus))
