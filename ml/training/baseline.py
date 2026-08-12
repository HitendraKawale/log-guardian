"""Measure the trivial baselines before fitting anything.

A model is only worth shipping if it beats the cheapest thing that works. On the
CRITICAL subset the bar is higher than it looks: the class is 41% positive, so
"alert on everything" already scores 0.59 F1 with perfect recall. This script
also runs the service's live HeuristicAnalyzer over the held-out window, which
is the honest way to find out whether the shipped scorer does anything at all.

    python ml/training/baseline.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services" / "ai-service"))

from app.analyzer import HeuristicAnalyzer  # noqa: E402
from app.schemas import AnalyzeRequest  # noqa: E402

from ml.data.prepare import TEST_PATH, TRAIN_PATH, read_jsonl  # noqa: E402

# A component is treated as alert-prone if it alerts more often than not in the
# training window. Derived from train only - reading test would leak.
COMPONENT_RULE_THRESHOLD = 0.5


def score_binary(y_true: list[int], y_pred: list[int]) -> tuple[float, float, float]:
    tp = sum(t == 1 and p == 1 for t, p in zip(y_true, y_pred, strict=True))
    fp = sum(t == 0 and p == 1 for t, p in zip(y_true, y_pred, strict=True))
    fn = sum(t == 1 and p == 0 for t, p in zip(y_true, y_pred, strict=True))

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def report(name: str, y_true: list[int], y_pred: list[int], y_score: list[float] | None) -> None:
    from sklearn.metrics import roc_auc_score

    precision, recall, f1 = score_binary(y_true, y_pred)
    auc = "     -"
    if y_score is not None and len(set(y_score)) > 1:
        auc = f"{roc_auc_score(y_true, y_score):6.3f}"
    print(f"  {name:<26s} {precision:9.3f} {recall:8.3f} {f1:8.3f} {auc:>8s}")


def alert_prone_components(train: list[dict]) -> set[str]:
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for record in train:
        counts[record["service"]][record["label"]] += 1
    return {
        service
        for service, (normal, alert) in counts.items()
        if alert / (normal + alert) > COMPONENT_RULE_THRESHOLD
    }


def main() -> None:
    for path in (TRAIN_PATH, TEST_PATH):
        if not path.exists():
            raise SystemExit(f"{path} not found - run: python ml/data/prepare.py")

    train = read_jsonl(TRAIN_PATH)
    test = read_jsonl(TEST_PATH)
    y_true = [r["label"] for r in test]
    prior = sum(y_true) / len(y_true)

    print(f"train {len(train):,} rows | test {len(test):,} rows | test prior {prior:.1%}\n")
    print(f"  {'baseline':<26s} {'precision':>9s} {'recall':>8s} {'f1':>8s} {'roc-auc':>8s}")

    report("always alert", y_true, [1] * len(test), None)
    report("never alert", y_true, [0] * len(test), None)

    # The scorer currently running in production, applied to real logs.
    analyzer = HeuristicAnalyzer()
    scores = [
        analyzer.analyze(
            AnalyzeRequest(
                service=r["service"],
                level=r["level"],
                message=r["message"],
                timestamp=r["timestamp"],
            )
        ).anomaly_score
        for r in test
    ]
    report(
        "shipped heuristic",
        y_true,
        [int(s >= HeuristicAnalyzer.threshold) for s in scores],
        scores,
    )

    prone = alert_prone_components(train)
    report(
        f"component in {sorted(prone)}",
        y_true,
        [int(r["service"] in prone) for r in test],
        None,
    )


if __name__ == "__main__":
    main()
