"""Profile the BGL dataset against the features the service already extracts.

Run this before touching the model. It answers one question: do the features
built for the synthetic generator carry any signal on real logs? The answer
decides what the modelling work actually is.

    python ml/data/profile_bgl.py
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services" / "ai-service"))

from app.features import keyword_count  # noqa: E402

from ml.data.bgl import ParseStats, load  # noqa: E402

DEFAULT_LOG = REPO_ROOT / "ml" / "datasets" / "BGL.log"


def _table(title: str, rows: dict[str, list[int]], key_header: str) -> None:
    print(f"\n{title}")
    print(f"  {key_header:<14s} {'normal':>12s} {'alert':>10s} {'alert rate':>12s}")
    for key, (normal, alert) in sorted(rows.items(), key=lambda kv: -sum(kv[1])):
        total = normal + alert
        print(f"  {key:<14s} {normal:12,d} {alert:10,d} {alert / total * 100:11.2f}%")


def profile(path: Path) -> None:
    stats = ParseStats()
    by_level: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_service: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_keywords: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    categories: Counter[str] = Counter()
    alerts = 0
    first = last = None

    for record in load(path, stats=stats):
        label = record["label"]
        alerts += label
        by_level[record["level"]][label] += 1
        by_service[record["service"]][label] += 1
        by_keywords[str(min(keyword_count(record["message"]), 2))][label] += 1
        if label:
            categories[record["category"]] += 1
        first = first or record["timestamp"]
        last = record["timestamp"]

    print(f"Parsed  : {stats}")
    print(f"Window  : {first:%Y-%m-%d} -> {last:%Y-%m-%d}")
    print(f"Alerts  : {alerts:,} of {stats.parsed:,} ({alerts / stats.parsed * 100:.2f}%)")

    _table("Severity vs. label", by_level, "level")
    _table("Component vs. label", dict(list(by_service.items())[:8]), "service")
    _table("RISK_KEYWORDS hits vs. label", by_keywords, "keywords")

    print(f"\nAlert categories: {len(categories)}")
    for name, count in categories.most_common(5):
        print(f"  {name:<14s} {count:10,d}")


if __name__ == "__main__":
    log_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOG
    if not log_path.exists():
        sys.exit(f"{log_path} not found - run: python ml/data/download.py")
    profile(log_path)
