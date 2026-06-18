"""Heuristic log anomaly scorer.

This is a deterministic, dependency-free stand-in for a real ML model. It maps
a log's level and message content to an anomaly score in ``[0, 1]``. Keeping it
deterministic makes the behaviour testable and gives the rest of the platform a
stable contract to build against while a trained model is developed under
``ml/``.
"""
from __future__ import annotations

from .schemas import AnalyzeRequest, AnalyzeResponse, Severity

# Baseline contribution of each log level to the anomaly score.
_LEVEL_WEIGHTS: dict[str, float] = {
    "DEBUG": 0.0,
    "INFO": 0.05,
    "WARNING": 0.30,
    "ERROR": 0.60,
    "CRITICAL": 0.85,
}

# Substrings that suggest a genuine problem. Each match nudges the score up.
_RISK_KEYWORDS: tuple[str, ...] = (
    "fail",
    "exception",
    "timeout",
    "timed out",
    "refused",
    "panic",
    "fatal",
    "unauthorized",
    "forbidden",
    "denied",
    "out of memory",
    "oom",
    "deadlock",
    "corrupt",
    "unreachable",
    "crash",
    "segfault",
    "traceback",
)

_KEYWORD_BOOST = 0.15
_ANOMALY_THRESHOLD = 0.70


def _severity_for(score: float) -> Severity:
    if score >= _ANOMALY_THRESHOLD:
        return Severity.HIGH
    if score >= 0.30:
        return Severity.MEDIUM
    return Severity.LOW


def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """Score a single log entry for anomalousness."""
    score = _LEVEL_WEIGHTS.get(request.level.value, 0.05)

    message = request.message.lower()
    matches = sum(1 for keyword in _RISK_KEYWORDS if keyword in message)
    score += matches * _KEYWORD_BOOST

    # Clamp into the valid range.
    score = max(0.0, min(1.0, round(score, 4)))

    return AnalyzeResponse(
        anomaly_score=score,
        is_anomaly=score >= _ANOMALY_THRESHOLD,
        predicted_severity=_severity_for(score),
    )
