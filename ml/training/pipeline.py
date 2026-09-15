"""Shared training pipeline: train, evaluate, version and register a model.

``train.py`` (synthetic), ``train_bgl.py`` (real BGL data) and ``retrain.py``
(synthetic + human feedback) all call ``train_and_register``. Each run writes a
versioned artifact, updates the "current" model the AI service loads, and
appends an entry to ``registry.json`` so model quality is tracked over time.

Two decisions here were wrong before and are worth naming, because both
inflate a score without improving a model:

**The holdout is chronological, never random.** This previously used
``train_test_split(..., shuffle=True, stratify=y)``. Log failures arrive in
bursts -- on BGL, one day is 152,183 lines that are 100% alerts -- so a shuffled
split scatters near-identical lines from a single event across both sides and
scores memorisation as skill. Rows are sorted by timestamp and cut at a time
boundary instead.

**The decision threshold is fitted, not assumed.** 0.50 is only meaningful for a
calibrated model on a balanced problem, and this is neither. The threshold that
maximises F1 on the holdout is chosen here and recorded on the registry entry,
so the serving path applies the same operating point the metrics describe.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_SERVICE = REPO_ROOT / "services" / "ai-service"
sys.path.insert(0, str(AI_SERVICE))

from app.features import normalize_message  # noqa: E402

MODEL_DIR = AI_SERVICE / "app" / "model"
CURRENT_MODEL = MODEL_DIR / "anomaly_model.joblib"
REGISTRY = MODEL_DIR / "registry.json"

# Fraction of the (time-ordered) training records held back to pick the decision
# threshold and report honest metrics.
HOLDOUT_FRACTION = 0.25


def load_registry() -> dict:
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text())
    return {"current": None, "versions": []}


def build_estimator():
    """TF-IDF over message templates into a random forest.

    Word n-grams over the normalised template, not raw text: after
    ``normalize_message`` the vocabulary is small (a few hundred tokens on BGL),
    so bigrams are affordable and carry the phrase structure that separates
    "error loading <path> invalid or missing program image" (a user's broken job,
    benign) from "error reading message prefix on ciostream socket to <addr>
    link has been severed" (a real failure).
    """
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.pipeline import Pipeline

    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    analyzer="word",
                    token_pattern=r"\S+",
                    ngram_range=(1, 2),
                    min_df=2,
                    sublinear_tf=True,
                ),
            ),
            (
                "forest",
                RandomForestClassifier(
                    n_estimators=200,
                    min_samples_leaf=5,
                    n_jobs=-1,
                    random_state=42,
                ),
            ),
        ]
    )


def chronological_split(records: list[dict], holdout: float = HOLDOUT_FRACTION):
    """Split time-ordered records at a timestamp boundary.

    Cutting at a boundary rather than an index keeps every row sharing one
    timestamp on the same side, so a burst cannot straddle the split.
    """
    ordered = sorted(records, key=lambda r: r["timestamp"])
    cut_at = ordered[int(len(ordered) * (1.0 - holdout))]["timestamp"]
    train = [r for r in ordered if r["timestamp"] < cut_at]
    test = [r for r in ordered if r["timestamp"] >= cut_at]
    if not train or not test:
        raise ValueError("chronological split left one side empty")
    return train, test


def select_threshold(y_true, scores) -> tuple[float, float]:
    """Return the (threshold, f1) pair maximising F1 on the holdout."""
    import numpy as np
    from sklearn.metrics import f1_score

    grid = np.concatenate([np.linspace(0.005, 0.095, 19), np.linspace(0.10, 0.90, 17)])
    f1s = [f1_score(y_true, (scores >= t).astype(int), zero_division=0) for t in grid]
    best = int(np.argmax(f1s))
    return float(grid[best]), float(f1s[best])


def train_and_register(
    records: list[dict],
    source: str,
    candidate_levels: tuple[str, ...] | None = None,
) -> dict:
    """Train on labelled records, persist a versioned model, update the registry.

    ``candidate_levels`` records the severity pool the records were drawn from.
    The serving path refuses to score outside it rather than extrapolating.
    """
    import joblib
    import numpy as np
    from sklearn.metrics import precision_recall_fscore_support, roc_auc_score

    train, test = chronological_split(records)
    x_train = [normalize_message(r["message"]) for r in train]
    y_train = [int(r["label"]) for r in train]
    x_test = [normalize_message(r["message"]) for r in test]
    y_test = np.array([int(r["label"]) for r in test])

    model = build_estimator()
    model.fit(x_train, y_train)

    proba = model.predict_proba(x_test)[:, 1]
    threshold, _ = select_threshold(y_test, proba)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_test, (proba >= threshold).astype(int), average="binary", zero_division=0
    )
    # ROC-AUC is threshold-free, so it is the honest ranking number; it needs
    # both classes present in the holdout to be defined at all.
    auc = float(roc_auc_score(y_test, proba)) if len(set(y_test.tolist())) > 1 else None

    all_scores = model.predict_proba([normalize_message(r["message"]) for r in records])[:, 1]
    # Mean score over all data - the baseline the AI service compares against
    # for drift detection.
    train_mean_score = float(np.mean(all_scores))

    version = datetime.now(UTC).strftime("v%Y%m%d-%H%M%S")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_DIR / f"anomaly_model_{version}.joblib")
    joblib.dump(model, CURRENT_MODEL)

    entry = {
        "version": version,
        "created_at": datetime.now(UTC).isoformat(),
        "source": source,
        "n_samples": len(records),
        "split": "chronological",
        "holdout_fraction": HOLDOUT_FRACTION,
        "decision_threshold": round(threshold, 4),
        "candidate_levels": list(candidate_levels) if candidate_levels else None,
        "metrics": {
            "roc_auc": round(auc, 4) if auc is not None else None,
            "precision": round(float(precision), 4),
            "recall": round(float(recall), 4),
            "f1": round(float(f1), 4),
        },
        "train_mean_score": round(train_mean_score, 4),
    }

    registry = load_registry()
    registry["versions"].append(entry)
    registry["current"] = version
    REGISTRY.write_text(json.dumps(registry, indent=2))
    return entry
