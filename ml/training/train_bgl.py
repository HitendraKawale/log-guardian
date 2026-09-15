"""Train the anomaly scorer on real BGL data and register it.

This is the entry point that produces the committed artifact. ``train.py`` still
exists and still trains on the synthetic generator, but a synthetic score is not
evidence of anything (the generator draws labels from the same variables the
featurizer reads) -- it is a smoke test that the pipeline runs.

    python ml/data/download.py     # once, 55 MB zipped
    python ml/data/prepare.py      # once, writes the chronological split
    python ml/training/train_bgl.py

Only the training split is read here. ``bgl_test.jsonl.gz`` is never opened by
this script; it is scored exactly once, by ``ml/training/evaluate.py``, after the
model is registered. The decision threshold comes from a chronological holdout
carved out of the *training* window, so choosing it costs no held-out data.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from ml.data.prepare import CANDIDATE_LEVEL, TRAIN_PATH, read_jsonl  # noqa: E402
from ml.training.pipeline import train_and_register  # noqa: E402


def main() -> None:
    if not TRAIN_PATH.exists():
        raise SystemExit(f"{TRAIN_PATH} not found - run: python ml/data/prepare.py")

    records = read_jsonl(TRAIN_PATH)
    positives = sum(r["label"] for r in records)
    print(
        f"Training on {len(records):,} {CANDIDATE_LEVEL} rows ({positives / len(records):.1%} alert)"
    )

    entry = train_and_register(
        records,
        source="bgl",
        candidate_levels=(CANDIDATE_LEVEL,),
    )
    print(f"Registered {entry['version']} (source: {entry['source']})")
    print(f"  threshold : {entry['decision_threshold']}")
    print(f"  holdout   : {entry['metrics']}")
    print("\nHoldout metrics are in-window. For the held-out five months run:")
    print("  python ml/training/evaluate.py")


if __name__ == "__main__":
    main()
