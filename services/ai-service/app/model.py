"""Loader for the trained anomaly-detection model.

The serialized model lives next to the service so it ships inside the Docker
image. If the artifact is missing (e.g. it hasn't been trained yet) loading
returns ``None`` and the service falls back to the heuristic scorer.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).parent / "model" / "anomaly_model.joblib"


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
