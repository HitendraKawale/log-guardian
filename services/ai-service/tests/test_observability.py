import json
import logging

from app.logging_config import JsonFormatter
from app.telemetry import tracing_enabled


def test_json_formatter_emits_valid_json():
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    payload = json.loads(JsonFormatter().format(record))
    assert payload["level"] == "INFO"
    assert payload["message"] == "hello world"
    assert payload["logger"] == "test"


def test_tracing_disabled_by_default(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_CONSOLE", raising=False)
    assert tracing_enabled() is False


def test_tracing_enabled_with_console_flag(monkeypatch):
    monkeypatch.setenv("OTEL_CONSOLE", "1")
    assert tracing_enabled() is True
