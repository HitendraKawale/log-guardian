"""Message templating -- the variant that was measured and **not** shipped.

Replacing the parts of a log line that vary between otherwise identical
messages (paths, socket addresses, node coordinates, hex words, numbers) with
placeholders is the standard first step in log anomaly detection: it is what
Drain and every parser built on it exist to do, and it collapses BGL's 884
distinct training lines into a few hundred families.

It also loses. On the held-out window it cost ROC-AUC against simply lowercasing
the raw message, and it cost most on the rows it was supposed to help:

    held-out rows with a NOVEL template (37.6%)   raw 0.9891   templated 0.9320

BGL's variable parts are not noise. ``ciod: Error loading /bgl/apps/SWL/...``
is a user's own broken job and carries no alert; the path segments are the
evidence for that, and ``<path>`` deletes them.

Kept because ``compare.py`` runs it as one of the parsers, and a rejected
approach with numbers attached is worth more than an unexamined assumption. It
is not imported by the service or by the shipped training path.
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
