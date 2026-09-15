"""Message templating: replace the parts of a log line that vary between
otherwise identical messages (paths, socket addresses, node coordinates, hex
words, numbers) with placeholders, so one message family collapses to one
string.

This is the single source of truth for templating. Two callers, opposite
verdicts, and the contrast is the point:

**The anomaly scorer rejected it.** Templating the message before fitting the
supervised model *lowered* held-out ROC-AUC on BGL, and lowered it most on the
rows it was meant to help -- 0.9891 raw against 0.9320 templated on held-out
lines whose template was never seen in training. BGL's variable parts are not
noise there: ``ciod: Error loading /bgl/apps/SWL/...`` is a user's own broken
job, and the path segments are the evidence for that. See
``docs/model-comparison.md``.

**The investigation trigger depends on it.** Novelty detection asks a different
question -- "have I seen this kind of line before?" -- and without templating
the answer is always no, because every new request id and file path makes a
line unique. Here collapsing the variable parts is exactly what makes the
question answerable.

``ml/training/compare.py`` imports this module to run it as one of the parsers
it compares, the same way the offline trainer imports the AI service's
featurizer.
"""

from __future__ import annotations

import re

# Ordered substitutions. Order is load-bearing: addresses and node coordinates
# must be consumed before the bare-number rule can eat their digits, and paths
# before punctuation is flattened.
_TEMPLATE_SUBSTITUTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    # IPv4, optionally with a port: 172.16.96.116:33399
    (re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?::\d+)?"), " <addr> "),
    # BlueGene/L hardware coordinates: R02-M1-N0-C:J12-U11. Case-insensitive
    # because substitution runs after lowercasing.
    (
        re.compile(r"\b[rjunmc][0-9]{1,2}(?:-[a-z][0-9]{1,2})+(?:[:-][a-z0-9]+)*", re.IGNORECASE),
        " <node> ",
    ),
    # Absolute filesystem paths (the dominant source of distinct lines).
    (re.compile(r"(?<![\w.])/[^\s:,()]{2,}"), " <path> "),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), " <hex> "),
    (re.compile(r"\b[0-9a-fA-F]{8,}\b"), " <hex> "),
    (re.compile(r"\b\d+\b"), " <num> "),
    # Flatten remaining punctuation so tokenisation is whitespace-only.
    (re.compile(r"[^\w<>]+"), " "),
    (re.compile(r"\s+"), " "),
)


def normalize_message(message: str) -> str:
    """Reduce a log message to its template. Deterministic and side-effect free."""
    text = message.lower()
    for pattern, replacement in _TEMPLATE_SUBSTITUTIONS:
        text = pattern.sub(replacement, text)
    return text.strip()
