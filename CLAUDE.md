# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
make install          # one shared .venv at the repo root for ALL suites
make test             # every suite that needs no infra: ai, ingestion, ml, contract, evals
make lint / format    # ruff over services/ ml/ evals/ (pinned 0.8.4 in CI — match it)
make up / down / logs # full stack via infrastructure/docker/docker-compose.yml
make demo-up / demo-down   # minimal demo stack (no Kafka/Grafana/k8s)
make train / retrain  # train on synthetic data (retrain needs INGESTION_URL)
make validate-corpus  # offline evidence/label consistency check, no model calls
make loadtest         # k6 against BASE_URL (default http://host.docker.internal:8000)
```

Suites, and what each one actually covers:

| Target | Directory | Needs |
| --- | --- | --- |
| `make test-ai` | `services/ai-service` | nothing |
| `make test-ingestion` | `services/ingestion-service` | nothing |
| `make test-ml` | `ml` | nothing |
| `make test-contract` | `tests/contract` | nothing — diffs the two services' JSON schemas |
| `make test-evals` | `evals` | nothing — validates the corpus, never calls a model |
| `make test-demo` | `demo` | nothing — in-process fault/recovery sandbox |
| `make test-integration` | `tests/integration` | `make up` |
| `make test-e2e` | `tests/e2e` | `make up` + chromium |

Tests **must run from their own directory** — each has its own `pytest.ini` with
`pythonpath = .`, and service imports are rooted at `app.*`:

```bash
cd services/ai-service        && ../../.venv/bin/python -m pytest tests/test_api.py::test_health -v
cd services/ingestion-service && ../../.venv/bin/python -m pytest -k investigation
cd evals                      && ../.venv/bin/python -m pytest
```

Local dev without Docker (ingestion defaults to a SQLite file, so no Postgres needed):

```bash
cd services/ai-service        && ../../.venv/bin/uvicorn app.main:app --port 8001
cd services/ingestion-service && AI_SERVICE_URL=http://localhost:8001 ../../.venv/bin/uvicorn app.main:app --port 8000
```

CI (`.github/workflows/ci.yml`) defines five jobs: lint, `kubectl kustomize
infrastructure/kubernetes`, a test matrix over the five infra-free suites above, an
integration job that stands up Compose and runs `tests/integration` + `tests/e2e`, and a
`python ml/training/train.py` smoke test. `demo/` has tests but is not in CI — a new
suite must be added to the matrix explicitly.

## Architecture

The repo is two things layered on each other: a **log ingestion platform** (two FastAPI
services + static frontend), and an **AI incident investigator** that reads that
platform's data through bounded read-only tools. The investigator is the headline work;
the platform is the substrate it investigates and the honest-negative ML case study.

### Ingestion platform

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
- The shipped scorer is a documented negative result: synthetic-trained, F1 0.588 /
  ROC-AUC 0.407 on real BGL data (identical to "always alert"). It is a display signal,
  not an investigation trigger. See `ml/README.md` and README "What the real data changed".

**Shared wire contract**: ingestion's `LogCreate`/`AIResponse` and the AI service's
`AnalyzeRequest`/`AnalyzeResponse` are intentionally identical, duplicated in two
`schemas.py`. Change both together or the services silently disagree —
`tests/contract` is what catches it.

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

### Investigation agent

All of it lives in `services/ingestion-service/app/investigation_*.py`, deliberately,
so the HTTP API, the worker, and the offline eval runner share one implementation.

- **`investigation_tools.py`** — `EvidenceTools`: four read-only tools (`query_logs`,
  `summarize_logs`, `search_runbooks`, `read_metric_series`) over *either* replay records
  *or* a live SQLAlchemy session, behind one contract. Owner-supplied construction
  parameters (source, `runbook_path`, session) are **never** model tool arguments.
  Metric reads use server-owned PromQL templates keyed by a `Literal` name; the model
  never supplies query text. Results are capped at 16 KiB, redacted, and carry explicit
  `truncated`/`error` markers. See `docs/evidence-tools.md`.
- **`investigation_schemas.py`** — scope is 1–4 services over ≤1 hour, offset-aware,
  `extra="forbid"` everywhere. Queries may narrow the authorized scope, never expand it.
- **`investigation_agent.py`** — systems **A** (one log query) and **B** (log query +
  full summary + runbook retrieval), each exactly one SDK request. Holds the shared
  `PROMPT`, the dated `PRICING` table, citation validation, and cost estimation.
  SDK retries are disabled so an ambiguous failed request is never counted as free.
- **`investigation_loop.py`** — system **C**, the adaptive agent: the model picks tools
  itself. Bounded at 6 model requests, 8 tool executions, 120s, 64 KiB evidence,
  1024 output tokens. Duplicate normalized queries, unknown tools, and malformed
  arguments stop the run.
- **`investigator.py`** — the worker process (`python -m app.investigator`), separate
  from the HTTP API. Claims queued rows atomically, records one ordered
  `InvestigationEvent` per tool call, enforces deadlines, and fails closed without
  `OPENAI_API_KEY`. Usage/timings live on the run row because this process does not
  share the API's `/metrics` registry.
- **`routes/investigations.py`** — queue/inspect/cancel only; **this process never calls
  the model**. Unlike log ingestion, an empty `INVESTIGATION_API_KEY` disables the API
  entirely (503), rather than leaving it open.

Every report claim must cite evidence IDs; unsupported causes must return
*inconclusive* with named missing evidence. Citation validation proves membership,
not entailment — semantic review is still a human step.

### Evaluation and demo

- **`evals/`** — the incident corpus (`cases/dev.jsonl`, `cases/test.jsonl`) plus
  `labels.jsonl`, which is **evaluator-only** and must never reach a prompt, tool result,
  retrieval index, runtime image, or public export. `validate.py` is stdlib-only and
  checks evidence/label consistency offline; `run.py` is the A/B/C runner. Preserved live
  artifacts are in `evals/results/<date>-<batch>/`, byte-for-byte with provenance.
- **`demo/`** — one small app deployed twice (checkout → inventory over real HTTP with a
  deadline), so an injected delay produces genuine 504s rather than scripted errors.
  Fault controls sit on a **separate localhost-bound port** and are never registered as
  agent tools; `run_scenario.py` is the only caller and always resets in `finally`.
- **`frontend/`** is dependency-free vanilla JS served by nginx; it polls the ingestion
  API and accepts an `?api=` base-URL override. **`site/`** is the generated read-only
  static demo — gitignored, rebuilt by `scripts/export_static_demo.py` from preserved
  eval artifacts. Edit `frontend/`, never `site/`.
- **`docs/evaluation.md`** is the complete scorecard. **`docs/plans/`** holds the approved
  technical plan, the delivery tracker, and one authorization record per paid batch.

## Conventions and gotchas

- **Paid model execution needs explicit per-batch authorization.** The pattern is a
  `docs/plans/*-authorization.md` recording model, run count, request ceiling, per-run and
  total allowance, and the frozen candidate revision — then a preserved
  `evals/results/` archive. Never start a live run, spend against an allowance, or reuse
  an exhausted one without the user saying so. `--dry-run` needs no key and no network.
- **Never tune on the held-out split.** `evals/cases/test.jsonl` has been consumed by one
  evaluation; further prompt/tool revisions driven by held-out failures require a *new*
  held-out set before any independence claim. Tune on `dev.jsonl`.
- **Results are archived, not edited.** Preserved run artifacts and their hashes are
  immutable evidence; failures stay in the denominator. Don't rewrite a `results/` file
  or a README's recorded numbers to look better.
- **Telemetry is opt-in** via `OTEL_EXPORTER_OTLP_ENDPOINT` (or `OTEL_CONSOLE=1`).
  `setup_telemetry` returns early otherwise, which is why tests and bare local runs need
  no collector. Keep new instrumentation behind `tracing_enabled()`.
- **Schema changes need an Alembic migration** (`services/ingestion-service/migrations/versions/`)
  *and* a `models.py` edit. `init_db`'s `create_all` still runs at startup for local SQLite,
  but containers run `alembic upgrade head`.
- **Model artifacts**: only `anomaly_model.joblib` and `registry.json` are committed;
  `anomaly_model_v*.joblib` is gitignored. Training appends to the registry — don't hand-edit it.
- **Security is off by default for logs, on by default for investigations**: `API_KEY=""`
  disables the `X-API-Key` dependency and `RATE_LIMIT_PER_MINUTE=0` disables the limiter,
  but an empty `INVESTIGATION_API_KEY` returns 503 everywhere. The rate limiter is
  in-process, so it is per-replica only.
- `infrastructure/kubernetes/monitoring-config/` duplicates root `monitoring/` because
  kustomize cannot read files outside its directory — **edit both** when changing
  Prometheus rules, Grafana dashboards, or Alertmanager config.
- ruff: line-length 100, `select = E,F,I,B,UP,C4`, target py311. `E501`/`B008` are ignored
  deliberately (formatter owns width; FastAPI needs `Depends()` in defaults). Any new
  Python directory must be added to the `lint` target and, if it has tests, to the CI matrix.
- Every module opens with a short docstring explaining the *why* of its design choice
  (best-effort AI calls, opt-in tracing, shared featurizer, worker/API separation).
  Match that when adding modules. Prose in this repo states limits plainly rather than
  overclaiming — keep that register in docs and READMEs.
- Branch per issue as `feat/<issue>-<slug>`, PR to `main`. Commit, push, and PR publication
  require the user's authorization each time (`docs/plans/2026-09-11-delivery-tracker.md`).
