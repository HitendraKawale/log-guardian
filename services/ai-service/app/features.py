"""Canonical feature extraction for log anomaly detection.

This module is the single source of truth for how a raw log entry is turned
into a numeric feature vector. Both the offline training pipeline (``ml/``) and
the online serving path import it, guaranteeing train/serve consistency.
"""
from __future__ import annotations

from datetime import datetime

# Ordinal encoding of log levels (higher = more severe).
LEVEL_ORDINAL: dict[str, int] = {
    "DEBUG": 0,
    "INFO": 1,
    "WARNING": 2,
    "ERROR": 3,
    "CRITICAL": 4,
}

# Substrings that suggest a genuine problem.
RISK_KEYWORDS: tuple[str, ...] = (
    "fail",
    "exception",
    "timeout",
    "timed out",
    "refused",
    "panic",
    "fatal",
    "unauthorized",
    "forbidden",
    "denied",
    "out of memory",
    "oom",
    "deadlock",
    "corrupt",
    "unreachable",
    "crash",
    "segfault",
    "traceback",
)

# Stable, ordered list of feature names produced by ``featurize``.
FEATURE_NAMES: tuple[str, ...] = (
    "level_ordinal",
    "message_length",
    "keyword_count",
    "digit_count",
    "hour_of_day",
)


def keyword_count(message: str) -> int:
    lowered = message.lower()
    return sum(1 for keyword in RISK_KEYWORDS if keyword in lowered)


def featurize(level: str, message: str, timestamp: datetime) -> list[float]:
    """Return the numeric feature vector for a single log entry."""
    return [
        float(LEVEL_ORDINAL.get(level.upper(), 1)),
        float(len(message)),
        float(keyword_count(message)),
        float(sum(char.isdigit() for char in message)),
        float(timestamp.hour),
    ]
