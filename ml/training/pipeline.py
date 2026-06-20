"""Shared training pipeline: train, evaluate, version and register a model.

Both ``train.py`` (synthetic only) and ``retrain.py`` (synthetic + human
feedback) call ``train_and_register``. Each run writes a versioned artifact,
updates the "current" model the AI service loads, and appends an entry to
``registry.json`` so model quality is tracked over time.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_SERVICE = REPO_ROOT / "services" / "ai-service"
sys.path.insert(0, str(AI_SERVICE))

from app.features import featurize  # noqa: E402

MODEL_DIR = AI_SERVICE / "app" / "model"
CURRENT_MODEL = MODEL_DIR / "anomaly_model.joblib"
REGISTRY = MODEL_DIR / "registry.json"


def load_registry() -> dict:
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text())
    return {"current": None, "versions": []}


def train_and_register(records: list[dict], source: str) -> dict:
    """Train on labelled records, persist a versioned model, update the registry."""
    import joblib
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import precision_recall_fscore_support, roc_auc_score
    from sklearn.model_selection import train_test_split

    X = [featurize(r["level"], r["message"], r["timestamp"]) for r in records]
    y = [int(r["label"]) for r in records]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )
    clf = RandomForestClassifier(n_estimators=120, max_depth=8, random_state=42, n_jobs=-1)
    clf.fit(X_train, y_train)

    proba = clf.predict_proba(X_test)[:, 1]
    preds = clf.predict(X_test)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_test, preds, average="binary", zero_division=0
    )
    # Mean score over all data — the baseline the AI service compares against
    # for drift detection.
    train_mean_score = float(np.mean(clf.predict_proba(X)[:, 1]))

    version = datetime.now(UTC).strftime("v%Y%m%d-%H%M%S")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, MODEL_DIR / f"anomaly_model_{version}.joblib")
    joblib.dump(clf, CURRENT_MODEL)

    entry = {
        "version": version,
        "created_at": datetime.now(UTC).isoformat(),
        "source": source,
        "n_samples": len(records),
        "metrics": {
            "roc_auc": round(float(roc_auc_score(y_test, proba)), 4),
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
