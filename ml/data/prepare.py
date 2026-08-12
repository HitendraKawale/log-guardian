"""Turn raw BGL into the train/test split the model is fitted on.

Two decisions are baked in here, both forced by what the data looks like.

**Only CRITICAL lines.** Every one of BGL's 348,460 alerts sits at CRITICAL
(FATAL/FAILURE upstream) and no alert appears at any lower severity, so a
severity check alone already gives perfect recall at ~41% precision. Scoring the
full 4.7M lines would just teach a model that rule. The open problem is which of
the 856k CRITICAL lines an operator actually treated as an alert.

**Split by time, never at random.** BGL failures arrive in bursts: 2005-06-12 is
152,183 lines that are 100% alerts, and two June days hold 62% of every alert in
the dataset. Shuffling puts near-identical lines from one event on both sides of
the split, so the model memorises the event and the score means nothing. The
cutoff below was chosen to keep a large held-out window whose class prior still
matches training (see ``--help`` for how to move it).

    python ml/data/prepare.py
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from ml.data.bgl import ParseStats, load  # noqa: E402

DATASET_DIR = REPO_ROOT / "ml" / "datasets"
RAW_LOG = DATASET_DIR / "BGL.log"
TRAIN_PATH = DATASET_DIR / "bgl_train.jsonl.gz"
TEST_PATH = DATASET_DIR / "bgl_test.jsonl.gz"

# Candidate pool: the severity gate the model sits behind.
CANDIDATE_LEVEL = "CRITICAL"

# 2005-09-01 holds out 26% of the pool across five months and four different
# alert regimes (Sep 44%, Oct 20%, Nov 61%, Jan 74%) while keeping the train and
# test priors within 1.3 points of each other. Later cutoffs shrink the test set;
# 2005-11-01 opens a 9-point prior gap.
DEFAULT_CUTOFF = "2005-09-01"


def write_jsonl(path: Path, records: Iterable[dict]) -> tuple[int, int]:
    """Write records as gzipped JSONL; return (count, positives)."""
    count = positives = 0
    with gzip.open(path, "wt") as handle:
        for record in records:
            row = dict(record, timestamp=record["timestamp"].isoformat())
            handle.write(json.dumps(row) + "\n")
            count += 1
            positives += record["label"]
    return count, positives


def read_jsonl(path: Path) -> list[dict]:
    """Load a prepared split back into memory, restoring timestamps."""
    with gzip.open(path, "rt") as handle:
        return [
            dict(row, timestamp=datetime.fromisoformat(row["timestamp"]))
            for row in map(json.loads, handle)
        ]


def prepare(raw: Path, cutoff: datetime) -> None:
    stats = ParseStats()
    candidates = [r for r in load(raw, stats=stats) if r["level"] == CANDIDATE_LEVEL]

    train = [r for r in candidates if r["timestamp"] < cutoff]
    test = [r for r in candidates if r["timestamp"] >= cutoff]
    if not train or not test:
        raise SystemExit(f"cutoff {cutoff:%Y-%m-%d} leaves one side empty")

    n_train, pos_train = write_jsonl(TRAIN_PATH, train)
    n_test, pos_test = write_jsonl(TEST_PATH, test)

    print(f"Parsed     : {stats}")
    print(f"Candidates : {len(candidates):,} {CANDIDATE_LEVEL} of {stats.parsed:,} parsed")
    print(f"Cutoff     : {cutoff:%Y-%m-%d}")
    print(f"  train -> {n_train:9,d} rows  {pos_train / n_train:6.1%} positive  {TRAIN_PATH.name}")
    print(f"  test  -> {n_test:9,d} rows  {pos_test / n_test:6.1%} positive  {TEST_PATH.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=RAW_LOG)
    parser.add_argument(
        "--cutoff",
        default=DEFAULT_CUTOFF,
        help=f"ISO date; rows on or after it are held out (default {DEFAULT_CUTOFF})",
    )
    args = parser.parse_args()

    if not args.raw.exists():
        raise SystemExit(f"{args.raw} not found - run: python ml/data/download.py")
    prepare(args.raw, datetime.fromisoformat(args.cutoff).replace(tzinfo=UTC))


if __name__ == "__main__":
    main()
