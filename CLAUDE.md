# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
make install          # one shared .venv at the repo root for BOTH services
make test             # both suites
make test-ai          # ai-service only
make test-ingestion   # ingestion-service only
make lint             # ruff check + ruff format --check over services/ and ml/
make format           # ruff --fix + format
make up / down / logs # full stack via infrastructure/docker/docker-compose.yml
make train            # train on synthetic data, register a new model version
make retrain          # synthetic + human feedback (needs INGESTION_URL)
make loadtest         # k6 against BASE_URL (default http://host.docker.internal:8000)
```

Tests **must run from the service directory** — each service has its own `pytest.ini`
with `pythonpath = .`, and imports are rooted at `app.*`:

```bash
cd services/ai-service        && ../../.venv/bin/python -m pytest tests/test_api.py::test_health -v
cd services/ingestion-service && ../../.venv/bin/python -m pytest -k feedback
```

Local dev without Docker (ingestion defaults to a SQLite file, so no Postgres needed):

```bash
cd services/ai-service        && ../../.venv/bin/uvicorn app.main:app --port 8001
cd services/ingestion-service && AI_SERVICE_URL=http://localhost:8001 ../../.venv/bin/uvicorn app.main:app --port 8000
```

CI (`.github/workflows/ci.yml`) runs four jobs: ruff (pinned **0.8.4** — match it),
`kubectl kustomize infrastructure/kubernetes`, both pytest suites, and a
`python ml/training/train.py` smoke test.

## Architecture

Two independently deployable FastAPI services plus a static frontend. The split keeps
the latency-sensitive write path away from model serving.

**ingestion-service** (`services/ingestion-service`, port 8000) — validate → score → persist.
- `app/service.py::persist_log` is the single scoring+persistence step. Both the REST
  route (`routes/logs.py`) and the Kafka worker (`app/consumer.py`) call it, so the
  synchronous and streaming paths are behaviourally identical. Put shared ingest logic here.
- `app/ai_client.py` calls are **best-effort**: any `httpx` error is swallowed and the log
  is stored with `status="unscored"` and null scores. Ingestion must never fail because
  the model is down — preserve this when touching the call path.
- Async SQLAlchemy 2.0. DB session and AI client are FastAPI dependencies
  (`get_session`, `get_ai_client`), which is how tests inject an in-memory SQLite engine
  and a `FakeAIClient` (`tests/conftest.py`).

**ai-service** (`services/ai-service`, port 8001) — stateless scorer, `POST /analyze`.
- `app/analyzer.py` picks `ModelAnalyzer` (trained `RandomForestClassifier`, threshold
  0.50) or `HeuristicAnalyzer` (level weights + keyword boost, threshold 0.70) **once at
  import time**. Whether `app/model/anomaly_model.joblib` exists therefore changes runtime
  behaviour; `heuristic_analyze()` exists as the deterministic entry point tests pin against.
- `app/features.py` is the **single source of truth for featurization**, imported by both
  serving and the offline trainer (`ml/training/pipeline.py` inserts `services/ai-service`
  onto `sys.path` to get it). Changing `FEATURE_NAMES`/`featurize` invalidates the committed
  model — retrain in the same change.

**Shared wire contract**: ingestion's `LogCreate`/`AIResponse` and the AI service's
`AnalyzeRequest`/`AnalyzeResponse` are intentionally identical, duplicated in two
`schemas.py`. Change both together or the services silently disagree.

**Streaming**: `POST /logs/stream` → Kafka `logs.raw` (202) → `log-consumer` (same image,
`python -m app.consumer`). Gated by `KAFKA_ENABLED`; off by default, on in Compose/k8s.
The producer injects W3C traceparent into message headers and the consumer extracts it,
so a streamed log is one trace across ingestion → consumer → AI service.

**MLOps loop**: dashboard labels → `POST /logs/{id}/feedback` → `GET /feedback/export` →
`ml/training/retrain.py` (oversamples feedback via `FEEDBACK_WEIGHT`) → `pipeline.py`
writes a versioned artifact, updates `anomaly_model.joblib`, and appends to
`app/model/registry.json` with metrics and a `train_mean_score` baseline. `app/drift.py`
compares a rolling window of live scores against that baseline and exports
`ai_score_drift`, which fires the `ModelDrift` alert.

## Conventions and gotchas

- **Telemetry is opt-in** via `OTEL_EXPORTER_OTLP_ENDPOINT` (or `OTEL_CONSOLE=1`).
  `setup_telemetry` returns early otherwise, which is why tests and bare local runs need
  no collector. Keep new instrumentation behind `tracing_enabled()`.
- **Schema changes need an Alembic migration** (`services/ingestion-service/migrations/versions/`)
  *and* a `models.py` edit. `init_db`'s `create_all` still runs at startup for local SQLite,
  but containers run `alembic upgrade head`.
- **Model artifacts**: only `anomaly_model.joblib` and `registry.json` are committed;
  `anomaly_model_v*.joblib` is gitignored. Training appends to the registry — don't hand-edit it.
- **Security is off by default**: `API_KEY=""` disables the `X-API-Key` dependency and
  `RATE_LIMIT_PER_MINUTE=0` disables the limiter. The rate limiter is in-process, so it is
  per-replica only.
- `infrastructure/kubernetes/monitoring-config/` duplicates root `monitoring/` because
  kustomize cannot read files outside its directory — **edit both** when changing
  Prometheus rules, Grafana dashboards, or Alertmanager config.
- ruff: line-length 100, `select = E,F,I,B,UP,C4`, target py311. `E501`/`B008` are ignored
  deliberately (formatter owns width; FastAPI needs `Depends()` in defaults).
- Existing modules carry a short docstring explaining the *why* of the design choice
  (best-effort AI calls, opt-in tracing, shared featurizer). Match that when adding modules.
- `frontend/` is dependency-free vanilla JS served by nginx; it polls the ingestion API
  and accepts an `?api=` base-URL override.
