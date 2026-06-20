"""Train the anomaly-detection model and export it for the AI service.

Run from the repo root:

    python ml/training/train.py

The model artifact is written into the AI service package so it ships inside
the service's Docker image. Feature extraction is imported from the AI service
to guarantee the exact same featurization is used for training and serving.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_SERVICE = REPO_ROOT / "services" / "ai-service"
# Import the canonical featurizer from the AI service package.
sys.path.insert(0, str(AI_SERVICE))

from app.features import FEATURE_NAMES, featurize  # noqa: E402
from generate_data import generate  # noqa: E402

MODEL_OUT = AI_SERVICE / "app" / "model" / "anomaly_model.joblib"


def main() -> None:
    import joblib
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import classification_report, roc_auc_score
    from sklearn.model_selection import train_test_split

    records = generate(n=4000)
    X = [featurize(r["level"], r["message"], r["timestamp"]) for r in records]
    y = [r["label"] for r in records]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    clf = RandomForestClassifier(n_estimators=120, max_depth=8, random_state=42, n_jobs=-1)
    clf.fit(X_train, y_train)

    proba = clf.predict_proba(X_test)[:, 1]
    print(f"Features: {list(FEATURE_NAMES)}")
    print(f"Test ROC-AUC: {roc_auc_score(y_test, proba):.3f}")
    print(classification_report(y_test, clf.predict(X_test), digits=3))

    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, MODEL_OUT)
    print(f"Saved model -> {MODEL_OUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
