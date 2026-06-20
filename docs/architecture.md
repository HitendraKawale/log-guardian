# Architecture

## Overview

Log Guardian is split into two independently deployable FastAPI services plus
supporting infrastructure. The split keeps the latency-sensitive ingestion path
separate from the (eventually heavier) model serving path.

## Ingestion service

Responsible for the write path:

1. Validate the incoming log against `LogCreate` (Pydantic).
2. Call the AI service to obtain an anomaly score (best-effort).
3. Persist the log plus score to the database.
4. Return the stored record.

Key design choices:

- **AI calls are best-effort.** A timeout or error from the AI service is logged
  and swallowed; the log is stored as `unscored` rather than failing the request.
  This keeps ingestion available even when the model is down.
- **Async SQLAlchemy 2.0.** Defaults to SQLite (zero-dependency local dev) and
  switches to Postgres via `DATABASE_URL` in Docker. `init_db` creates tables on
  startup; production should move to Alembic migrations.
- **Dependency injection** for the DB session and AI client makes both trivially
  mockable — the test suite swaps in a `FakeAIClient` and an in-memory database.

## AI service

A stateless scorer with two interchangeable strategies behind one interface:

- **`ModelAnalyzer`** wraps a `RandomForestClassifier` trained under `ml/` and
  uses its predicted probability as the anomaly score. The model loads from
  `app/model/anomaly_model.joblib` at startup.
- **`HeuristicAnalyzer`** is a deterministic fallback (level baseline + risk
  keywords), used automatically when no model artifact is present. It keeps the
  service useful out of the box and is what the deterministic tests pin.

Feature extraction (`features.py`) is shared between training and serving so the
two never drift. Both strategies clamp the score to `[0, 1]` and derive
`is_anomaly` / `predicted_severity` from thresholds, keeping the
`AnalyzeRequest` / `AnalyzeResponse` contract stable. `GET /health` reports which
strategy is active.

## Frontend

A dependency-free static dashboard (`frontend/`, served by nginx) that polls the
ingestion API: stat cards, a live log table with colour-coded severity and score
bars, and a form to ingest test logs. It talks to the API over CORS and takes an
optional `?api=` override for the base URL.

## Shared contract

The ingestion service's `LogCreate` and the AI service's `AnalyzeRequest` are
intentionally identical, as are the response shapes. The services communicate
over JSON HTTP; timestamps are serialized in ISO-8601.

## Observability

Both services expose Prometheus metrics at `/metrics`:

- `ingestion_logs_total`, `ingestion_anomalous_logs_total`
- `ai_analyze_requests_total`, `ai_anomalies_detected_total`, `ai_anomaly_score`

Prometheus scrapes both; Grafana visualizes them.

## Failure modes

| Failure | Behaviour |
| --- | --- |
| AI service down/slow | Log stored as `unscored`, request still succeeds (201) |
| Database down | `/readiness` fails; ingestion returns 500 |
| Invalid payload | 422 with validation detail |

## Streaming

Besides the synchronous `POST /logs`, an optional Kafka path decouples ingestion
from scoring for higher throughput. `POST /logs/stream` publishes the raw log to
the `logs.raw` topic and returns `202` immediately. The `log-consumer` worker
(`app/consumer.py`, run as a separate process from the same image) consumes the
topic and calls `persist_log` — the exact same scoring/persistence used by the
REST route, so both paths are behaviourally identical. Kafka is gated behind
`KAFKA_ENABLED` so the service runs fine without a broker.

## Deployment

- **Docker Compose** (`infrastructure/docker`) runs the full stack including
  Kafka, the consumer, and the monitoring stack.
- **Kubernetes** (`infrastructure/kubernetes`) deploys the core tier — Postgres,
  AI service, ingestion (with a HorizontalPodAutoscaler) and frontend behind an
  ingress. The ingestion image applies Alembic migrations on startup.
