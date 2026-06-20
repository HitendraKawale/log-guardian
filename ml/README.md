# ML

Training pipeline for Log Guardian's anomaly-detection model.

The model is a `RandomForestClassifier` trained on synthetic, labelled logs. It
predicts the probability that a log entry is an anomaly. Feature extraction is
imported from `services/ai-service/app/features.py` so training and serving use
identical features.

## Train

```bash
pip install -r ml/requirements.txt
pip install -r services/ai-service/requirements.txt   # for the featurizer
python ml/training/train.py
```

This writes `services/ai-service/app/model/anomaly_model.joblib` (the current
model the AI service loads, with a heuristic fallback if absent) and appends an
entry to `registry.json` with the metrics for that version.

## Feedback loop

Users label logs from the dashboard; those labels are stored and exposed at the
ingestion service's `/feedback/export`. Retraining folds them back in:

```bash
INGESTION_URL=http://localhost:8000 python ml/training/retrain.py
```

This pulls the labelled examples, oversamples them (`FEEDBACK_WEIGHT`, default
50) so they actually influence the model, merges them with the synthetic set,
retrains, and registers a new `synthetic+feedback` version. The AI service
reports the active version and metric history at `GET /model/info`.

## Model registry

`services/ai-service/app/model/registry.json` tracks every trained version —
created time, source, sample count, metrics (ROC-AUC, precision, recall, F1) and
a `train_mean_score` baseline used for drift detection. Versioned `.joblib`
artifacts are written next to it but git-ignored; only the current model and the
registry are committed.

## Layout

```
ml/
  training/
    generate_data.py   synthetic labelled log generator
    pipeline.py        train -> evaluate -> version -> register
    train.py           train on synthetic data
    retrain.py         train on synthetic + human feedback
  datasets/            (place real datasets here)
  requirements.txt
```
