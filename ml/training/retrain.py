"""Retrain the model on synthetic data plus collected human feedback.

Pulls labelled examples from the ingestion service's ``/feedback/export``
endpoint, merges them with the synthetic dataset, retrains, and registers a new
model version. Run from the repo root:

    INGESTION_URL=http://localhost:8000 python ml/training/retrain.py

Because real feedback is scarce relative to the synthetic set, each feedback
example is oversampled (``FEEDBACK_WEIGHT``) so it actually moves the model.
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime

from generate_data import generate
from pipeline import train_and_register

INGESTION_URL = os.getenv("INGESTION_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "")
FEEDBACK_WEIGHT = int(os.getenv("FEEDBACK_WEIGHT", "50"))


def fetch_feedback() -> list[dict]:
    request = urllib.request.Request(f"{INGESTION_URL}/feedback/export?limit=10000")
    if API_KEY:
        request.add_header("X-API-Key", API_KEY)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def to_records(feedback: list[dict]) -> list[dict]:
    records = []
    for item in feedback:
        timestamp = item["timestamp"].replace("Z", "+00:00")
        records.append(
            {
                "service": item["service"],
                "level": item["level"],
                "message": item["message"],
                "timestamp": datetime.fromisoformat(timestamp),
                "label": 1 if item["true_label"] else 0,
            }
        )
    return records


def main() -> None:
    synthetic = generate(n=4000)

    try:
        feedback = to_records(fetch_feedback())
    except Exception as exc:
        print(f"Could not fetch feedback ({exc}); training on synthetic data only.")
        feedback = []

    print(f"{len(feedback)} feedback examples (oversampled x{FEEDBACK_WEIGHT})")
    records = synthetic + feedback * FEEDBACK_WEIGHT
    source = "synthetic+feedback" if feedback else "synthetic"

    entry = train_and_register(records, source=source)
    print(f"Registered {entry['version']} (source: {entry['source']})")
    print(f"Metrics: {entry['metrics']}")


if __name__ == "__main__":
    main()
