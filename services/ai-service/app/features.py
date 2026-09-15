"""Canonical feature extraction for log anomaly detection.

This module is the single source of truth for how a raw log entry becomes model
input. Both the offline training pipeline (``ml/``) and the online serving path
import it, guaranteeing train/serve consistency.

A message is reduced to a **template**: the parts that vary between otherwise
identical lines (socket addresses, node coordinates, filesystem paths, hex words,
bare numbers) are replaced with placeholders, so every line in one message family
collapses onto a single string. That matters because BGL's variable part is
almost always a path or an address — ``ciod: Error loading /home/x/a.rts`` and
``ciod: Error loading /p/gb2/y/b.rts`` are the same event. Abstracting them
raises the share of held-out lines whose family was seen during training from
18% to 59%, which is the difference between a model that generalises and one
that memorises June 2005.

The numeric features this module used to export (level ordinal, message length,
digit count, hour of day) are gone. Measured on the real BGL split, *every one of
them lowered* held-out ROC-AUC when added to the template text — ``hour_of_day``
worst of all, because it lets the model memorise when the failure bursts
happened rather than what they said. ``ml/README.md`` records the ablation.
"""

from __future__ import annotations

import re

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

# Ordered template substitutions. Order is load-bearing: addresses and node
# coordinates must be consumed before the bare-number rule can eat their digits,
# and paths before punctuation is flattened.
_TEMPLATE_SUBSTITUTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    # IPv4, optionally with a port: 172.16.96.116:33399
    (re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?::\d+)?"), " <addr> "),
    # BlueGene/L hardware coordinates: R02-M1-N0-C:J12-U11. Case-insensitive
    # because substitution runs after lowercasing.
    (
        re.compile(r"\b[rjunmc][0-9]{1,2}(?:-[a-z][0-9]{1,2})+(?:[:-][a-z0-9]+)*", re.IGNORECASE),
        " <node> ",
    ),
    # Absolute filesystem paths (the dominant source of spurious distinct lines).
    (re.compile(r"(?<![\w.])/[^\s:,()]{2,}"), " <path> "),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), " <hex> "),
    (re.compile(r"\b[0-9a-fA-F]{8,}\b"), " <hex> "),
    (re.compile(r"\b\d+\b"), " <num> "),
    # Flatten remaining punctuation so tokenisation is whitespace-only.
    (re.compile(r"[^\w<>]+"), " "),
    (re.compile(r"\s+"), " "),
)


def keyword_count(message: str) -> int:
    lowered = message.lower()
    return sum(1 for keyword in RISK_KEYWORDS if keyword in lowered)


def normalize_message(message: str) -> str:
    """Reduce a log message to its template.

    Deterministic and side-effect free: the same message always yields the same
    template, which is what lets the offline trainer and the serving path agree.
    """
    text = message.lower()
    for pattern, replacement in _TEMPLATE_SUBSTITUTIONS:
        text = pattern.sub(replacement, text)
    return text.strip()
