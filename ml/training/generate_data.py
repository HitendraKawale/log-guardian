"""Synthetic log dataset generator.

Produces labelled log entries with a learnable but noisy relationship between a
log's features (level, message content, time of day) and whether it is an
anomaly. This stands in for real labelled production logs while the platform is
being built.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
_LEVEL_WEIGHTS = [0.30, 0.40, 0.15, 0.10, 0.05]
_LEVEL_ORDINAL = {lvl: i for i, lvl in enumerate(LEVELS)}

_NORMAL_MESSAGES = [
    "request completed in {n}ms",
    "user {n} logged in",
    "cache hit for key user:{n}",
    "health check ok",
    "processed {n} records",
    "scheduled job finished successfully",
    "served static asset",
    "background sync complete",
]

_ANOMALOUS_MESSAGES = [
    "database connection refused after {n}ms",
    "request failed with status 500",
    "unhandled exception in request handler",
    "read timeout after {n}ms",
    "out of memory: killed process {n}",
    "permission denied for user {n}",
    "deadlock detected on table orders",
    "upstream service unreachable",
    "fatal panic: segfault in worker {n}",
]


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def generate(n: int = 4000, seed: int = 42) -> list[dict]:
    """Generate ``n`` labelled log records as dicts."""
    rng = random.Random(seed)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    records: list[dict] = []

    for _ in range(n):
        level = rng.choices(LEVELS, weights=_LEVEL_WEIGHTS, k=1)[0]
        ordinal = _LEVEL_ORDINAL[level]

        # Higher levels are more likely to carry an anomalous-looking message.
        p_anomalous_msg = {0: 0.03, 1: 0.05, 2: 0.40, 3: 0.80, 4: 0.90}[ordinal]
        anomalous_msg = rng.random() < p_anomalous_msg
        pool = _ANOMALOUS_MESSAGES if anomalous_msg else _NORMAL_MESSAGES
        message = rng.choice(pool).format(n=rng.randint(1, 99999))

        timestamp = start + timedelta(
            days=rng.randint(0, 120),
            hours=rng.randint(0, 23),
            minutes=rng.randint(0, 59),
        )
        off_hours = timestamp.hour < 6 or timestamp.hour >= 22

        # Latent anomaly likelihood with noise; the model must recover this from
        # the engineered features rather than from this hidden value.
        latent = 0.6 * (ordinal / 4) + (0.4 if anomalous_msg else 0.0)
        latent += 0.05 if off_hours else 0.0
        prob = _sigmoid(7.0 * (latent - 0.5))
        label = 1 if rng.random() < prob else 0

        records.append(
            {
                "service": rng.choice(["payment-api", "auth", "gateway", "worker"]),
                "level": level,
                "message": message,
                "timestamp": timestamp,
                "label": label,
            }
        )

    return records


if __name__ == "__main__":
    sample = generate(10)
    for record in sample:
        print(record["label"], record["level"], record["message"])
