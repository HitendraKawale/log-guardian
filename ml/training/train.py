"""Train the anomaly-detection model on synthetic data and register it.

Run from the repo root:

    python ml/training/train.py

Writes a versioned artifact, updates the current model the AI service loads,
and records metrics in ``services/ai-service/app/model/registry.json``.
"""

from __future__ import annotations

from generate_data import generate
from pipeline import train_and_register


def main() -> None:
    records = generate(n=4000)
    entry = train_and_register(records, source="synthetic")
    print(f"Registered {entry['version']} from {entry['n_samples']} samples")
    print(f"Metrics: {entry['metrics']}")


if __name__ == "__main__":
    main()
