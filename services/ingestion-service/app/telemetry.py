"""OpenTelemetry setup.

Tracing is opt-in: it only activates when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set
(or ``OTEL_CONSOLE=1`` for local span printing). When disabled the service runs
exactly as before, so tests and dependency-free local runs are unaffected.

FastAPI, httpx and SQLAlchemy are auto-instrumented, so an incoming request, the
downstream call to the AI service, and the database queries all appear as spans
in a single distributed trace.
"""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def tracing_enabled() -> bool:
    return bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or os.getenv("OTEL_CONSOLE"))


def setup_telemetry(app, service_name: str, sqlalchemy_engine=None) -> None:
    if not tracing_enabled():
        return

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        url = endpoint.rstrip("/") + "/v1/traces"
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=url)))
    else:
        from opentelemetry.sdk.trace.export import (
            ConsoleSpanExporter,
            SimpleSpanProcessor,
        )

        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)

    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    HTTPXClientInstrumentor().instrument()

    if sqlalchemy_engine is not None:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument(engine=sqlalchemy_engine.sync_engine)
