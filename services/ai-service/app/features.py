"""Canonical feature extraction for log anomaly detection.

This module is the single source of truth for how a raw log entry becomes model
input. Both the offline training pipeline (``ml/``) and the online serving path
import it, guaranteeing train/serve consistency.

The transformation is deliberately almost nothing: lowercase the message and
hand it to the vectorizer. That is not laziness, it is a measured result. The
obvious move for log data is to template it first -- replace paths, addresses
and numbers with placeholders so one message family collapses to one string,
which is what every log-parsing paper does. Measured on the real BGL split, it
made the model *worse*, and worst exactly where it was supposed to help: on
held-out lines whose template was never seen in training, ROC-AUC fell from
0.989 to 0.932. Abstracting less beat abstracting more at every level tested.

The reason is that BGL's "variable" parts are not noise. ``ciod: Error loading
/bgl/apps/...`` is a user's broken job and benign; the path segments carry that
signal, and replacing them with ``<path>`` throws it away. The template variant
lives in ``ml/training/templates.py`` and is still run by
``ml/training/compare.py``, which is where the comparison is recorded.

The numeric features this module used to export (level ordinal, message length,
digit count, hour of day) are also gone: every one of them lowered held-out
ROC-AUC when added to the text, ``hour_of_day`` worst of all, because it lets
the model memorise when the June 2005 bursts happened rather than what they
said. ``ml/README.md`` records both ablations.
"""

from __future__ import annotations

# Substrings that suggest a genuine problem. Retained for ``HeuristicAnalyzer``,
# the dependency-free fallback scorer -- not used by the trained model, whose
# vocabulary is learned from data. On BGL these keywords are anti-correlated
# with real alerts, which is precisely why the heuristic scores below chance.
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


def keyword_count(message: str) -> int:
    lowered = message.lower()
    return sum(1 for keyword in RISK_KEYWORDS if keyword in lowered)


def prepare_message(message: str) -> str:
    """Return the exact text handed to the vectorizer.

    Trivial today, but it is the seam that keeps the offline trainer and the
    serving path in agreement. Anything that changes here invalidates the
    committed model, so change it and retrain in the same breath.
    """
    return message.lower()
