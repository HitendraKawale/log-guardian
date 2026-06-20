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

This writes `services/ai-service/app/model/anomaly_model.joblib`, which the AI
service loads on startup (falling back to a heuristic scorer if absent).

## Layout

```
ml/
  training/
    generate_data.py   synthetic labelled log generator
    train.py           trains and exports the model
  datasets/            (place real datasets here)
  requirements.txt
```
