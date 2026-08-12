"""The two services duplicate their wire contract on purpose. This checks it.

``LogCreate`` in the ingestion service and ``AnalyzeRequest`` in the AI service
describe the same JSON, as do ``AIResponse`` and ``AnalyzeResponse``. Neither
service imports the other, which is what keeps them independently deployable
and is also what lets them drift apart silently: add a field on one side and
nothing fails until a real request is rejected in production.

Both schemas modules are import-free apart from pydantic, so they load straight
from disk under separate module names without the two ``app`` packages
colliding.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
INGESTION_SCHEMAS = REPO_ROOT / "services" / "ingestion-service" / "app" / "schemas.py"
AI_SCHEMAS = REPO_ROOT / "services" / "ai-service" / "app" / "schemas.py"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ingestion = _load("ingestion_schemas", INGESTION_SCHEMAS)
ai = _load("ai_schemas", AI_SCHEMAS)


def _shape(model) -> tuple[dict, list]:
    """A model's schema minus its name, so two differently-named twins compare."""
    schema = model.model_json_schema()
    return schema["properties"], sorted(schema.get("required", []))


def test_request_contract_matches():
    assert _shape(ingestion.LogCreate) == _shape(ai.AnalyzeRequest)


def test_response_contract_matches():
    assert _shape(ingestion.AIResponse) == _shape(ai.AnalyzeResponse)


def test_log_levels_match():
    assert [level.value for level in ingestion.LogLevel] == [level.value for level in ai.LogLevel]


def test_severities_match():
    assert [s.value for s in ingestion.Severity] == [s.value for s in ai.Severity]


def test_request_fields_are_what_the_services_actually_send():
    # Pins the contract itself, so a coordinated change on both sides still has
    # to be deliberate rather than accidental.
    properties, required = _shape(ingestion.LogCreate)
    assert set(properties) == {"service", "level", "message", "timestamp"}
    assert required == ["level", "message", "service", "timestamp"]


def test_response_fields_are_what_the_services_actually_return():
    properties, required = _shape(ai.AnalyzeResponse)
    assert set(properties) == {"anomaly_score", "is_anomaly", "predicted_severity"}
    assert required == ["anomaly_score", "is_anomaly", "predicted_severity"]
