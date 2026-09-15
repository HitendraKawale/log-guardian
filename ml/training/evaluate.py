"""Score the registered model on the held-out BGL window.

Kept separate from training on purpose. ``train_bgl.py`` never opens the test
split; this script never fits anything. The threshold it applies is the one
recorded on the registry entry, chosen on a holdout inside the training window,
so nothing here is tuned against the five months it reports on.

    python ml/training/evaluate.py

Every number printed is measured on rows the model has not seen, in a window
that starts after every row it was fitted on.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_SERVICE = REPO_ROOT / "services" / "ai-service"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(AI_SERVICE))

from app.features import normalize_message  # noqa: E402
from app.model import MODEL_PATH, current_version  # noqa: E402

from ml.data.prepare import TEST_PATH, read_jsonl  # noqa: E402


def main() -> None:
    import joblib
    import numpy as np
    from sklearn.metrics import precision_recall_fscore_support, roc_auc_score

    if not MODEL_PATH.exists():
        raise SystemExit(f"{MODEL_PATH} not found - run: python ml/training/train_bgl.py")
    if not TEST_PATH.exists():
        raise SystemExit(f"{TEST_PATH} not found - run: python ml/data/prepare.py")

    entry = current_version() or {}
    threshold = float(entry.get("decision_threshold", 0.50))
    model = joblib.load(MODEL_PATH)

    records = read_jsonl(TEST_PATH)
    y_true = np.array([int(r["label"]) for r in records])
    scores = model.predict_proba([normalize_message(r["message"]) for r in records])[:, 1]
    predictions = (scores >= threshold).astype(int)

    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, predictions, average="binary", zero_division=0
    )
    auc = roc_auc_score(y_true, scores)

    print(f"model      : {entry.get('version', '?')} (source: {entry.get('source', '?')})")
    print(f"threshold  : {threshold}")
    print(f"held out   : {len(records):,} rows, {y_true.mean():.1%} alert")
    print(f"  {'metric':<12s}{'value':>8s}")
    print(f"  {'precision':<12s}{precision:8.3f}")
    print(f"  {'recall':<12s}{recall:8.3f}")
    print(f"  {'f1':<12s}{f1:8.3f}")
    print(f"  {'roc-auc':<12s}{auc:8.3f}")
    print("\nThe bar to beat (see ml/training/baseline.py): f1 0.588, roc-auc 0.500.")


if __name__ == "__main__":
    main()
