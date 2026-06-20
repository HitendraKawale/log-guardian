"""Loader for the trained anomaly-detection model.

The serialized model lives next to the service so it ships inside the Docker
image. If the artifact is missing (e.g. it hasn't been trained yet) loading
returns ``None`` and the service falls back to the heuristic scorer.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent / "model"
MODEL_PATH = MODEL_DIR / "anomaly_model.joblib"
REGISTRY_PATH = MODEL_DIR / "registry.json"


def load_registry() -> dict:
    """Return the model registry (current version + metric history)."""
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text())
    return {"current": None, "versions": []}


def current_version() -> dict | None:
    registry = load_registry()
    return next((v for v in registry["versions"] if v["version"] == registry["current"]), None)


def load_model() -> Any | None:
    if not MODEL_PATH.exists():
        logger.info("No trained model at %s; using heuristic scorer.", MODEL_PATH)
        return None
    try:
        import joblib

        model = joblib.load(MODEL_PATH)
        logger.info("Loaded anomaly model from %s", MODEL_PATH)
        return model
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to load model (%s); using heuristic scorer.", exc)
        return None
