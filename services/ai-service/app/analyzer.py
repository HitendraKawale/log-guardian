"""Log anomaly scoring.

Two interchangeable strategies implement the same interface:

* ``ModelAnalyzer`` wraps a trained scikit-learn classifier and uses its
  predicted probability as the anomaly score.
* ``HeuristicAnalyzer`` is a deterministic, dependency-free fallback used when
  no trained model is available. It also keeps the service useful out of the box.

``analyze()`` dispatches to whichever strategy is active at import time.
"""

from __future__ import annotations

from .features import keyword_count, normalize_message
from .model import current_version, load_model
from .schemas import AnalyzeRequest, AnalyzeResponse, Severity


def _severity_for(score: float, threshold: float) -> Severity:
    """Grade severity by how far past the decision threshold a score sits.

    The bands used to be fixed at 0.70/0.30, which silently assumed the scorer
    flags at ~0.50. A fitted threshold breaks that assumption: the BGL model
    flags at 0.025, so under fixed bands a score twelve times its threshold
    still reads "medium" and nothing below 0.70 could ever read "high".
    Measuring the margin into the [threshold, 1] band keeps severity meaningful
    for any operating point, including the heuristic's 0.70.
    """
    if score < threshold:
        return Severity.LOW
    margin = (score - threshold) / (1.0 - threshold) if threshold < 1.0 else 1.0
    if margin >= 0.50:
        return Severity.HIGH
    if margin >= 0.15:
        return Severity.MEDIUM
    return Severity.LOW


def _build_response(score: float, threshold: float) -> AnalyzeResponse:
    score = max(0.0, min(1.0, round(score, 4)))
    return AnalyzeResponse(
        anomaly_score=score,
        is_anomaly=score >= threshold,
        predicted_severity=_severity_for(score, threshold),
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
    """Wraps a trained message-template pipeline exposing ``predict_proba``.

    Two things come from the registry entry rather than being hardcoded, because
    both are properties of the data the artifact was fitted on:

    ``decision_threshold``
        Chosen by maximising F1 on a chronological holdout at training time. The
        old fixed 0.50 was arbitrary; on BGL it costs roughly 0.35 F1.
    ``candidate_levels``
        The severity pool the model saw. A model fitted only on CRITICAL lines
        has no evidence about INFO lines, so rather than extrapolate it scores
        anything outside the pool 0.0 -- the severity gate stays an explicit
        rule, which is all the data supports (every BGL alert is CRITICAL).
    """

    name = "model"
    threshold = 0.50

    def __init__(
        self,
        model,
        threshold: float = 0.50,
        candidate_levels: tuple[str, ...] | None = None,
    ) -> None:
        self._model = model
        self.threshold = threshold
        self._candidate_levels = candidate_levels

    def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        if self._candidate_levels and request.level.value not in self._candidate_levels:
            return _build_response(0.0, self.threshold)
        # Probability of the positive (anomaly) class.
        score = float(self._model.predict_proba([normalize_message(request.message)])[0][1])
        return _build_response(score, self.threshold)


def _select_analyzer():
    model = load_model()
    if model is None:
        return HeuristicAnalyzer()
    entry = current_version() or {}
    levels = entry.get("candidate_levels")
    return ModelAnalyzer(
        model,
        threshold=float(entry.get("decision_threshold", 0.50)),
        candidate_levels=tuple(levels) if levels else None,
    )


# Active analyzer, chosen once at import time.
active_analyzer = _select_analyzer()


def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    return active_analyzer.analyze(request)


# Kept as a stable, deterministic entry point for tests and as the documented
# fallback behaviour, independent of whether a model is loaded.
def heuristic_analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    return HeuristicAnalyzer().analyze(request)
