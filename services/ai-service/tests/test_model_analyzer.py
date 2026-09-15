"""ModelAnalyzer behaviour, pinned against a stub so it holds for any artifact.

These cover the two things the trained path does that the heuristic does not:
refuse to score severities it was never fitted on, and apply the threshold that
was fitted alongside it rather than a hardcoded 0.50.
"""

from datetime import UTC, datetime

import pytest
from app.analyzer import ModelAnalyzer, _severity_for
from app.schemas import AnalyzeRequest, LogLevel, Severity


class StubModel:
    """Returns a fixed positive-class probability, ignoring its input."""

    def __init__(self, score: float) -> None:
        self.score = score
        self.seen: list[str] = []

    def predict_proba(self, texts):
        self.seen.extend(texts)
        return [[1.0 - self.score, self.score] for _ in texts]


def _req(level: LogLevel, message: str = "data TLB error interrupt") -> AnalyzeRequest:
    return AnalyzeRequest(
        service="kernel", level=level, message=message, timestamp=datetime.now(UTC)
    )


def test_model_receives_the_prepared_message():
    model = StubModel(0.9)
    ModelAnalyzer(model).analyze(_req(LogLevel.CRITICAL, "Error loading /home/a/b.rts"))
    assert model.seen == ["error loading /home/a/b.rts"]


def test_score_below_fitted_threshold_is_not_an_anomaly():
    result = ModelAnalyzer(StubModel(0.02), threshold=0.025).analyze(_req(LogLevel.CRITICAL))
    assert result.is_anomaly is False


def test_score_above_fitted_threshold_is_an_anomaly_even_though_it_is_small():
    """0.03 would not be an anomaly under the old hardcoded 0.50."""
    result = ModelAnalyzer(StubModel(0.03), threshold=0.025).analyze(_req(LogLevel.CRITICAL))
    assert result.is_anomaly is True


def test_level_outside_the_candidate_pool_is_not_scored():
    model = StubModel(0.99)
    analyzer = ModelAnalyzer(model, threshold=0.025, candidate_levels=("CRITICAL",))
    result = analyzer.analyze(_req(LogLevel.INFO))
    assert result.anomaly_score == pytest.approx(0.0)
    assert result.is_anomaly is False
    assert model.seen == [], "the model must not be consulted outside its severity pool"


def test_level_inside_the_candidate_pool_is_scored():
    analyzer = ModelAnalyzer(StubModel(0.99), threshold=0.025, candidate_levels=("CRITICAL",))
    assert analyzer.analyze(_req(LogLevel.CRITICAL)).is_anomaly is True


def test_no_candidate_pool_means_every_level_is_scored():
    analyzer = ModelAnalyzer(StubModel(0.99), threshold=0.025)
    assert analyzer.analyze(_req(LogLevel.INFO)).is_anomaly is True


@pytest.mark.parametrize(
    ("score", "threshold", "expected"),
    [
        (0.00, 0.025, Severity.LOW),  # below threshold
        (0.03, 0.025, Severity.LOW),  # flagged, but barely
        (0.20, 0.025, Severity.MEDIUM),
        (1.00, 0.025, Severity.HIGH),
        (0.85, 0.700, Severity.HIGH),  # the heuristic's operating point
        (0.60, 0.700, Severity.LOW),  # below the heuristic threshold
    ],
)
def test_severity_scales_with_the_margin_past_the_threshold(score, threshold, expected):
    assert _severity_for(score, threshold) is expected
