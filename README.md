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
| `ingestion-service` | 8000 | Validate logs, call the AI service, persist, expose them |
| `ai-service` | 8001 | Score a log's anomaly likelihood and severity |
| `postgres` | 5432 | Durable log storage |
| `prometheus` | 9090 | Scrape `/metrics` from both services |
| `grafana` | 3000 | Dashboards (admin/admin) |

## Quick start (Docker)

```bash
make up        # build + start the whole stack
make logs      # tail logs
make down      # stop
```

Then open the interactive API docs at <http://localhost:8000/docs>.

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

- `POST /logs` — ingest and score a log
- `GET /logs?limit=&offset=` — list logs (newest first)
- `GET /logs/{id}` — fetch one log
- `GET /health` · `GET /readiness` · `GET /metrics`

AI service:

- `POST /analyze` — score a log (`anomaly_score`, `is_anomaly`, `predicted_severity`)
- `GET /health` · `GET /metrics`

## Tests

```bash
make test            # both suites
make test-ai
make test-ingestion
```

## Repository layout

```
services/
  ingestion-service/   FastAPI app, DB models, AI client, tests
  ai-service/          FastAPI app, heuristic analyzer, tests
infrastructure/
  docker/              docker-compose.yml
  kubernetes/          (placeholder for k8s manifests)
monitoring/
  prometheus/          scrape config
  grafana/             (placeholder for dashboards)
ml/                    datasets & training for a future learned model
docs/                  architecture notes
```

## Roadmap

- Replace the heuristic analyzer with a trained model (see `ml/`).
- Alembic migrations instead of `create_all`.
- Grafana dashboards provisioned as code.
- Kubernetes manifests under `infrastructure/kubernetes`.

See [`docs/architecture.md`](docs/architecture.md) for design details.
