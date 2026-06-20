"""Log anomaly scoring.

Two interchangeable strategies implement the same interface:

* ``ModelAnalyzer`` wraps a trained scikit-learn classifier and uses its
  predicted probability as the anomaly score.
* ``HeuristicAnalyzer`` is a deterministic, dependency-free fallback used when
  no trained model is available. It also keeps the service useful out of the box.

``analyze()`` dispatches to whichever strategy is active at import time.
"""

from __future__ import annotations

from .features import featurize, keyword_count
from .model import load_model
from .schemas import AnalyzeRequest, AnalyzeResponse, Severity


def _severity_for(score: float) -> Severity:
    if score >= 0.70:
        return Severity.HIGH
    if score >= 0.30:
        return Severity.MEDIUM
    return Severity.LOW


def _build_response(score: float, threshold: float) -> AnalyzeResponse:
    score = max(0.0, min(1.0, round(score, 4)))
    return AnalyzeResponse(
        anomaly_score=score,
        is_anomaly=score >= threshold,
        predicted_severity=_severity_for(score),
    )


class HeuristicAnalyzer:
    """Deterministic level + keyword scorer."""

    name = "heuristic"
    threshold = 0.70

    _LEVEL_WEIGHTS = {
        "DEBUG": 0.0,
        "INFO": 0.05,
        "WARNING": 0.30,
        "ERROR": 0.60,
        "CRITICAL": 0.85,
    }
    _KEYWORD_BOOST = 0.15

    def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        score = self._LEVEL_WEIGHTS.get(request.level.value, 0.05)
        score += keyword_count(request.message) * self._KEYWORD_BOOST
        return _build_response(score, self.threshold)


class ModelAnalyzer:
    """Wraps a trained classifier exposing ``predict_proba``."""

    name = "model"
    threshold = 0.50

    def __init__(self, model) -> None:
        self._model = model

    def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        features = [featurize(request.level.value, request.message, request.timestamp)]
        # Probability of the positive (anomaly) class.
        score = float(self._model.predict_proba(features)[0][1])
        return _build_response(score, self.threshold)


def _select_analyzer():
    model = load_model()
    if model is not None:
        return ModelAnalyzer(model)
    return HeuristicAnalyzer()


# Active analyzer, chosen once at import time.
active_analyzer = _select_analyzer()


def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    return active_analyzer.analyze(request)


# Kept as a stable, deterministic entry point for tests and as the documented
# fallback behaviour, independent of whether a model is loaded.
def heuristic_analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    return HeuristicAnalyzer().analyze(request)
