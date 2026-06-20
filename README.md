# Log Guardian

AI-assisted log monitoring platform. Services ingest application logs, score each
entry for anomalies using an AI analysis service, persist the results, and expose
metrics for Prometheus and Grafana.

```
                 ┌──────────────────┐        ┌──────────────────┐
   logs ───────▶ │ ingestion-service│ ─────▶ │    ai-service    │
                 │   (FastAPI)      │ ◀───── │ anomaly scoring  │
                 └────────┬─────────┘ score  └──────────────────┘
                          │ persist
                          ▼
                 ┌──────────────────┐        ┌──────────────────┐
                 │    PostgreSQL    │        │ Prometheus+Grafana│
                 └──────────────────┘        └──────────────────┘
```

## Services

| Service | Port | Responsibility |
| --- | --- | --- |
| `frontend` | 8080 | Web dashboard to watch logs & anomalies live |
| `ingestion-service` | 8000 | Validate logs, call the AI service, persist, expose them |
| `ai-service` | 8001 | Score a log with a trained model (heuristic fallback) |
| `postgres` | 5432 | Durable log storage |
| `kafka` | 9092 | Streaming ingestion buffer |
| `log-consumer` | – | Consumes streamed logs, scores & persists them |
| `prometheus` | 9090 | Scrape `/metrics`, evaluate alert rules |
| `grafana` | 3000 | Provisioned dashboards (admin/admin) |
| `jaeger` | 16686 | Distributed traces across the services |

## Quick start (Docker)

```bash
make up        # build + start the whole stack
make logs      # tail logs
make down      # stop
```

Then open:

- **Dashboard** — <http://localhost:8080>
- **API docs** — <http://localhost:8000/docs>
- **Grafana** — <http://localhost:3000> (admin/admin)
- **Prometheus** — <http://localhost:9090>

## Quick start (local, no Docker)

```bash
make install                      # venv + dev deps for both services

# terminal 1 — AI service
cd services/ai-service && ../../.venv/bin/uvicorn app.main:app --port 8001

# terminal 2 — ingestion service
cd services/ingestion-service && \
  AI_SERVICE_URL=http://localhost:8001 ../../.venv/bin/uvicorn app.main:app --port 8000
```

By default the ingestion service uses a local SQLite database, so no Postgres is
required for local development.

## Example

```bash
curl -X POST http://localhost:8000/logs \
  -H 'Content-Type: application/json' \
  -d '{
        "service": "payment-api",
        "level": "CRITICAL",
        "message": "Database connection refused, request failed",
        "timestamp": "2026-06-18T10:00:00Z"
      }'
```

```json
{
  "id": 1, "service": "payment-api", "level": "CRITICAL",
  "message": "Database connection refused, request failed",
  "timestamp": "2026-06-18T10:00:00", "status": "scored",
  "anomaly_score": 1.0, "is_anomaly": true, "predicted_severity": "high"
}
```

If the AI service is unavailable the log is still stored, with `status:
"unscored"` and null scores, so ingestion never blocks on the model.

## API

Ingestion service:

- `POST /logs` — ingest and score a log (synchronous)
- `POST /logs/stream` — publish a log to Kafka for async scoring (202)
- `GET /logs?limit=&offset=&service=&level=&anomalous=` — list/filter logs
- `GET /logs/{id}` — fetch one log
- `POST /logs/{id}/feedback` — attach a human label (`{"is_anomaly": bool}`)
- `GET /feedback/export` — labelled examples for retraining
- `GET /model/info` — active model version + metrics (proxied from the AI service)
- `GET /health` · `GET /readiness` · `GET /metrics`

AI service:

- `POST /analyze` — score a log (`anomaly_score`, `is_anomaly`, `predicted_severity`)
- `GET /model/info` — current model version, metric history, drift
- `GET /health` · `GET /metrics`

## Anomaly model

The AI service scores logs with a `RandomForestClassifier` trained on synthetic
labelled logs. If no model artifact is present it transparently falls back to a
deterministic heuristic, so the service always works. Retrain with:

```bash
pip install -r ml/requirements.txt
python ml/training/train.py     # writes services/ai-service/app/model/
```

### Feedback loop (MLOps)

The model improves from use:

1. Reviewers label logs from the dashboard (anomaly / normal).
2. Labels are stored and served at `GET /feedback/export`.
3. `make retrain` folds them back in (oversampled), retrains, and registers a
   new `synthetic+feedback` model version.
4. Every version is tracked in `registry.json` (metrics + a score baseline); the
   AI service serves the current one and reports it at `GET /model/info`.
5. The AI service watches the live score distribution against that baseline and
   fires a `ModelDrift` alert when it diverges.

See [`ml/README.md`](ml/README.md) for details.

## Database migrations

Schema is managed with Alembic (the container runs `alembic upgrade head` on
start). Locally:

```bash
cd services/ingestion-service && alembic upgrade head
```

## Monitoring

Prometheus scrapes both services and evaluates alert rules
(`monitoring/prometheus/alerts.yml`: service down, high anomaly rate, no logs,
model drift). Grafana auto-provisions the **Log Guardian** dashboard from
`monitoring/grafana/`.

### Tracing & structured logs

Both services are instrumented with **OpenTelemetry**. A request is traced end
to end — incoming HTTP, the call to the AI service, and the database queries all
appear as spans in one trace at <http://localhost:16686> (Jaeger). Streamed logs
carry their trace context through Kafka, so the consumer's work joins the same
trace. Logs are emitted as JSON with the active `trace_id`/`span_id` for
correlation. Tracing is opt-in via `OTEL_EXPORTER_OTLP_ENDPOINT` (set in
Compose; unset everywhere else, so tests and local runs are unaffected).

## Tests & CI

```bash
make test            # both suites
make test-ai
make test-ingestion
```

GitHub Actions (`.github/workflows/ci.yml`) runs both suites and a model-training
smoke test on every push and PR.

## Repository layout

```
frontend/              static web dashboard (served by nginx)
services/
  ingestion-service/   FastAPI app, DB models, AI client, migrations, tests
  ai-service/          FastAPI app, model + heuristic analyzer, tests
infrastructure/
  docker/              docker-compose.yml
  kubernetes/          (placeholder for k8s manifests)
monitoring/
  prometheus/          scrape config + alert rules
  grafana/             provisioned datasource + dashboard
ml/                    synthetic data + model training pipeline
docs/                  architecture notes
.github/workflows/     CI
```

## Streaming

A high-throughput async path: `POST /logs/stream` publishes to Kafka and returns
immediately; the `log-consumer` worker scores and persists out of band, reusing
the same `persist_log` logic as the synchronous route. Enabled via
`KAFKA_ENABLED=true` (on by default in Compose).

## Kubernetes

Manifests for the core tier (Postgres, AI, ingestion + HPA, frontend, ingress)
live in [`infrastructure/kubernetes`](infrastructure/kubernetes/README.md):

```bash
kubectl apply -k infrastructure/kubernetes
```

## Roadmap

- [x] Trained model with heuristic fallback (`ml/`)
- [x] Alembic migrations instead of `create_all`
- [x] Grafana dashboards & Prometheus alerts provisioned as code
- [x] Web dashboard
- [x] Kubernetes manifests under `infrastructure/kubernetes`
- [x] Kafka streaming ingestion
- [x] Feedback loop: human labels → retrain → versioned registry → drift alerts
- [x] Distributed tracing + structured logs (OpenTelemetry + Jaeger)
- [ ] Kafka + monitoring stack manifests for Kubernetes

See [`docs/architecture.md`](docs/architecture.md) for design details.
