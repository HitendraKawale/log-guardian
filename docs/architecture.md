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

A stateless scorer. The current `analyzer.py` is a deterministic heuristic:

- Each log level contributes a baseline score.
- Risk keywords in the message (`failed`, `timeout`, `refused`, ...) add to it.
- The score is clamped to `[0, 1]`; `is_anomaly` and `predicted_severity` are
  derived from thresholds.

Being deterministic makes it fully testable and gives the platform a stable
contract while a learned model is developed under `ml/`. Swapping in a real model
only requires changing `analyze()` to keep the same `AnalyzeRequest` /
`AnalyzeResponse` contract.

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
