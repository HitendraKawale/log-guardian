"""Lightweight data-drift tracking.

Compares the mean anomaly score over a rolling window of recent requests against
the ``train_mean_score`` baseline recorded when the model was trained. A large
gap suggests the live traffic distribution has drifted from the training data
and the model may need retraining. Exposed as Prometheus gauges and via
``/model/info``.
"""

from __future__ import annotations

from collections import deque

from prometheus_client import Gauge

from .model import current_version

RECENT_MEAN = Gauge("ai_recent_anomaly_score_mean", "Mean anomaly score over recent requests")
DRIFT = Gauge(
    "ai_score_drift", "Absolute gap between the recent mean score and the training baseline"
)


class DriftTracker:
    def __init__(self, window: int = 200) -> None:
        self._scores: deque[float] = deque(maxlen=window)
        version = current_version()
        self._baseline = version["train_mean_score"] if version else 0.0

    def observe(self, score: float) -> None:
        self._scores.append(score)
        RECENT_MEAN.set(self.recent_mean)
        DRIFT.set(self.drift)

    @property
    def baseline(self) -> float:
        return self._baseline

    @property
    def recent_mean(self) -> float:
        return sum(self._scores) / len(self._scores) if self._scores else 0.0

    @property
    def drift(self) -> float:
        return abs(self.recent_mean - self._baseline)


tracker = DriftTracker()
