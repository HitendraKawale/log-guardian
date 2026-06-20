import json
import logging

from app.logging_config import JsonFormatter
from app.telemetry import tracing_enabled


def test_json_formatter_emits_valid_json():
    record = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="boom",
        args=(),
        exc_info=None,
    )
    payload = json.loads(JsonFormatter().format(record))
    assert payload["level"] == "WARNING"
    assert payload["message"] == "boom"


def test_tracing_disabled_by_default(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_CONSOLE", raising=False)
    assert tracing_enabled() is False


def test_tracing_enabled_with_endpoint(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4318")
    assert tracing_enabled() is True
