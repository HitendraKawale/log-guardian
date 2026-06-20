from datetime import datetime, timezone

import pytest

# These tests pin the deterministic heuristic behaviour, which is the
# documented fallback regardless of whether a trained model is loaded.
from app.analyzer import heuristic_analyze as analyze
from app.schemas import AnalyzeRequest, LogLevel, Severity


def _req(level: LogLevel, message: str = "routine heartbeat") -> AnalyzeRequest:
    return AnalyzeRequest(
        service="payment-api",
        level=level,
        message=message,
        timestamp=datetime.now(timezone.utc),
    )


def test_debug_is_low_severity():
    result = analyze(_req(LogLevel.DEBUG))
    assert result.predicted_severity is Severity.LOW
    assert result.is_anomaly is False
    assert result.anomaly_score == pytest.approx(0.0)


def test_critical_is_high_severity_anomaly():
    result = analyze(_req(LogLevel.CRITICAL))
    assert result.predicted_severity is Severity.HIGH
    assert result.is_anomaly is True


def test_keywords_increase_score():
    plain = analyze(_req(LogLevel.WARNING, "cache miss"))
    risky = analyze(_req(LogLevel.WARNING, "connection refused, request failed"))
    assert risky.anomaly_score > plain.anomaly_score


def test_keyword_matching_is_case_insensitive():
    lower = analyze(_req(LogLevel.ERROR, "timeout reached"))
    upper = analyze(_req(LogLevel.ERROR, "TIMEOUT reached"))
    assert lower.anomaly_score == upper.anomaly_score


def test_score_is_clamped_to_one():
    result = analyze(
        _req(LogLevel.CRITICAL, "fatal panic: oom crash, deadlock, corrupt, segfault")
    )
    assert result.anomaly_score <= 1.0


def test_analysis_is_deterministic():
    req = _req(LogLevel.ERROR, "database connection failed")
    assert analyze(req).model_dump() == analyze(req).model_dump()
