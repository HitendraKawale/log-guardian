"""Measure the label-free investigation trigger against the labelled baselines.

The trigger needs no labels to run. Labels are used here only to score it, the
same way you would grade any candidate-selection rule after the fact.

    python ml/training/measure_trigger.py

Two questions, and the second matters more than the first:

1. On BGL's held-out window, does the trigger surface each alerting message
   family at least once, and at what review volume?

   Per-ROW recall is the wrong metric here and is reported only to show why: the
   trigger fires once per family by design, and a single BGL alert family spans
   up to 39,696 rows, so per-row recall punishes precisely the de-duplication
   that makes a trigger useful. An on-call engineer wants one candidate per
   novel failure mode, not 39,696.

2. On application logs -- the traffic the demo sandbox actually emits -- does it
   do anything at all? The supervised scorer scores 0.0 there by construction,
   because it was fitted on CRITICAL supercomputer RAS lines and refuses to
   extrapolate. If the trigger is also useless outside BGL then it has not
   solved the problem it exists to solve, and this prints that plainly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_SERVICE = REPO_ROOT / "services" / "ai-service"
INGESTION = REPO_ROOT / "services" / "ingestion-service"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(INGESTION))

from app.trigger import InvestigationTrigger  # noqa: E402

from ml.data.prepare import TEST_PATH, read_jsonl  # noqa: E402

DEMO_BUNDLE = REPO_ROOT / "demo" / "bundles" / "2026-09-14-demo-incident.json"


def score(y_true: list[int], flagged: list[int]) -> tuple[float, float, float]:
    tp = sum(t == 1 and p == 1 for t, p in zip(y_true, flagged, strict=True))
    fp = sum(t == 0 and p == 1 for t, p in zip(y_true, flagged, strict=True))
    fn = sum(t == 1 and p == 0 for t, p in zip(y_true, flagged, strict=True))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def run_trigger(records: list[dict], warmup: int) -> list[int]:
    """Replay records through the trigger in time order, as ingestion would."""
    trigger = InvestigationTrigger(warmup_logs=warmup)
    flagged = []
    for record in records:
        candidate = trigger.consider(
            service=record["service"],
            level=record["level"],
            message=record["message"],
            timestamp=record["timestamp"],
        )
        flagged.append(int(candidate is not None))
    return flagged


def report(name: str, y_true: list[int], flagged: list[int]) -> None:
    precision, recall, f1 = score(y_true, flagged)
    volume = sum(flagged) / len(flagged) if flagged else 0.0
    print(
        f"  {name:<34s}{precision:9.3f}{recall:8.3f}{f1:8.3f}" f"{sum(flagged):>10,d}{volume:9.1%}"
    )


def measure_bgl() -> None:
    if not TEST_PATH.exists():
        print(f"  (skipped: {TEST_PATH.name} not found - run ml/data/prepare.py)")
        return
    from app.templates import normalize_message

    records = sorted(read_jsonl(TEST_PATH), key=lambda r: r["timestamp"])
    y_true = [int(r["label"]) for r in records]
    flagged = run_trigger(records, warmup=500)
    print(f"\nBGL held-out window: {len(records):,} rows, {sum(y_true) / len(y_true):.1%} alert")

    # Per-family: of the message families that contain at least one alert, how
    # many did the trigger surface? This is the question a trigger answers.
    families: dict[str, bool] = {}
    caught: set[str] = set()
    for record, hit in zip(records, flagged, strict=True):
        template = normalize_message(record["message"])
        families[template] = families.get(template, False) or bool(record["label"])
        if hit:
            caught.add(template)
    alerting = {t for t, has_alert in families.items() if has_alert}
    benign = set(families) - alerting
    found = len(alerting & caught)
    noise = len(benign & caught)

    print(f"  message families: {len(families):,}  ({len(alerting):,} contain an alert)")
    print(
        f"  alerting families surfaced : {found:,}/{len(alerting):,} = {found / len(alerting):.1%}"
    )
    print(f"  benign families surfaced   : {noise:,}/{len(benign):,}  (review cost)")
    print(
        f"  candidates raised          : {sum(flagged):,} = {sum(flagged) / len(records):.2%} of rows"
    )
    print(f"  precision over candidates  : {found / max(1, len(caught)):.1%}")

    print("\n  Per-row, for contrast (the wrong metric, see the module docstring):")
    print(
        f"  {'rule':<34s}{'precision':>9s}{'recall':>8s}{'f1':>8s}"
        f"{'flagged':>10s}{'volume':>9s}"
    )
    report("always alert", y_true, [1] * len(records))
    report("trigger: unseen template", y_true, flagged)
    print("\n  The supervised scorer reaches f1 0.973 here and needs 633,977 labelled rows.")
    print("  The trigger needs none, and raises a review queue of the size shown above.")


def measure_application_logs() -> None:
    """The case the supervised model cannot serve at all."""
    print("\nApplication logs (demo sandbox capture)")
    if not DEMO_BUNDLE.exists():
        print(f"  (skipped: {DEMO_BUNDLE.relative_to(REPO_ROOT)} not found)")
        return

    from datetime import datetime

    bundle = json.loads(DEMO_BUNDLE.read_text())
    logs = bundle.get("logs", bundle if isinstance(bundle, list) else [])
    records = [
        {
            "service": entry["service"],
            "level": entry["level"],
            "message": entry["message"],
            "timestamp": datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00")),
        }
        for entry in logs
    ]
    if not records:
        print("  (no logs in bundle)")
        return
    records.sort(key=lambda r: r["timestamp"])

    # A short capture cannot afford a 500-line warmup; state the value used.
    warmup = min(20, len(records) // 4)
    flagged = run_trigger(records, warmup=warmup)
    levels = sorted({r["level"] for r in records})
    print(f"  {len(records):,} logs, levels {levels}, warmup {warmup}")
    print(f"  candidates: {sum(flagged)} ({sum(flagged) / len(records):.1%} of the capture)")
    print("  These logs carry no alert labels, so this is coverage, not accuracy.")
    if not sum(flagged):
        print("  NOTHING FLAGGED - the trigger is inert on this traffic.")
    else:
        for record, hit in zip(records, flagged, strict=True):
            if hit:
                print(f"    [{record['level']:<8s}] {record['service']}: {record['message'][:78]}")


def main() -> None:
    measure_bgl()
    measure_application_logs()


if __name__ == "__main__":
    main()
