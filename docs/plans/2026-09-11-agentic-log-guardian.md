# Log Guardian: an AI engineer portfolio plan

> Approved through Plannotator. Execute in issue-linked slices; see [delivery tracker](2026-09-11-delivery-tracker.md).
> At execution time, use `executing-plans` and split each phase into a session-sized implementation checklist. Do not commit unless asked.

## Context

Today, Log Guardian scores individual logs but cannot investigate an incident.
Build a read-only agent that gathers evidence, tests explanations, and produces a cited incident report.
Prove its value against a fixed retrieval workflow, then demonstrate it on a controlled application failure.

Audience: hiring teams for applied AI engineering roles. This plan prioritizes LLM tool use, retrieval, evaluation, reliability, and a usable product. It does not claim to qualify the project as frontier-model research or model-training infrastructure.

## Approach

Keep the name. Change the product description to:

> Log Guardian investigates service failures using logs and runbooks, shows the evidence behind its findings, and stops when it cannot support a diagnosis.

Build one evidence-backed investigation agent and one complete workflow. Keep BGL classification as a separate ML case study. Use fixed retrieval as the evaluation baseline.

Do not use a team of agents to imitate an operations team. Compare a bounded single-agent loop with a cheaper fixed workflow before adding orchestration complexity.

## What the project already has

Reviewed at commit `87f280f`. The working tree was clean before this plan.

| Area | Evidence in the repo | Keep or change |
| --- | --- | --- |
| Ingestion | `services/ingestion-service/app/service.py::persist_log` serves both REST and Kafka. `ai_client.py` catches HTTP and response-validation errors. | Keep. No LLM calls on either ingestion path. Best-effort scoring can still delay persistence while the HTTP call is in flight; it is not asynchronous scoring. |
| Storage and contracts | SQLAlchemy models, two Alembic revisions, deliberately duplicated scoring schemas, contract tests. | Extend ingestion-owned storage for investigations. Leave the scoring wire contract unchanged. |
| Current AI | Five scalar features and a Random Forest. `app/model/registry.json` identifies the active artifact as synthetic. | Keep as an explicitly labeled experimental signal, never proof of root cause or the sole investigation trigger. |
| Real-data work | BGL parser, chronological split, and baseline runner are implemented. The training commands still use generated data. | Preserve the analysis. BGL anomaly labels are not root-cause labels for the new agent. |
| Feedback | Binary anomaly labels feed `retrain.py`. It oversamples feedback before the random split. | Do not reuse these labels as agent-quality judgments. Duplicate feedback can cross the train/test split; fix before using that pipeline for quality claims. |
| Dashboard | `frontend/app.js` fetches 50 filtered rows every three seconds. Stats describe those rows, not the whole system. | Replace the main workflow with investigation selection, progress, and evidence. Keep logs as a secondary view and label their scope. |
| Demo | `scripts/seed_demo.py` samples independent messages and copies model predictions into some feedback labels. | Useful display filler, not connected incidents or independent ground truth. Keep it out of evaluations. |
| Observability | OpenTelemetry across HTTP and Kafka. Prometheus scrapes the two HTTP services. | Reuse tracing. Current metrics describe Log Guardian, not payment or inventory services mentioned in seeded messages. |
| Deployment | Compose, Kubernetes, monitoring, load-test artifacts. | Keep the full stack optional. Start the new workflow without requiring Kafka or Kubernetes. |
| Tests | Service, ML, contract, integration, and browser suites. | Extend existing suites rather than introducing another testing framework. |

Review coverage: first-party application code, training/data code, tests, scripts, migrations, configuration, deployment manifests, monitoring, documentation, and committed desktop/mobile screenshots. The six Kubernetes monitoring copies were byte-compared with their root counterparts and are identical. Binary model internals, the full raw BGL corpus, and video frames were not manually inspected. The prepared BGL splits were exercised by the baseline runner.

### Fresh baseline evidence

Commands ran locally while planning:

```text
make test
23 passed in 1.36s
26 passed in 0.14s
12 passed in 0.01s
6 passed in 0.06s

make lint
All checks passed!
57 files already formatted

kubectl kustomize infrastructure/kubernetes
kustomize render: OK

.venv/bin/python ml/training/baseline.py
train 633,977 rows | test 222,395 rows | test prior 41.6%
  baseline                   precision   recall       f1  roc-auc
  always alert                   0.416    1.000    0.588        -
  never alert                    0.000    0.000    0.000        -
  shipped heuristic              0.416    1.000    0.588    0.407
  component in ['bglmaster', 'linkcard', 'monitor']     0.107    0.002    0.004        -
```

The total is 67 passing local tests. Several suites emit the existing pytest-asyncio fixture-loop-scope deprecation warning.

Not run: Docker builds, live integration/browser suites, fault injection, fresh load tests, model training, or paid LLM calls. This review does not certify a running deployment. Training would replace the current artifact and append to the registry, so it was deliberately not run.

Some existing tests prove less than their descriptions suggest: the browser feedback test checks for absence of `?`, not the saved label; the migration integration test checks columns, not the Alembic revision; the split test duplicates the cutoff expression rather than calling `prepare`. Repair these assertions when their flows enter the implementation scope.

## The product someone should see

A hiring manager opens a saved investigation without entering a provider key.

1. Select a clearly labeled replay: "Checkout requests began timing out at 14:03 UTC."
2. See a bounded service/time scope and click **Investigate** in an owner-authorized live session.
3. Watch actual tool activity: summarize the window, inspect upstream logs, retrieve the timeout runbook, inspect a contradictory clue.
4. Read a report separating observed symptoms, the best-supported explanation, alternatives, and missing evidence.
5. Click each citation to inspect the exact evidence the agent received.
6. See model/version, elapsed time, tool-call count, token usage, and estimated cost.
7. Open an inconclusive case and see the agent request missing evidence instead of inventing a fix.

The final demonstration adds a real timeout between two local demo services. Replays remain available for fast, repeatable browsing. Mark replay, live, and recorded results explicitly. Never animate a recording as if it were a current model run.

Suggested actions are text for an operator. There is no execution or approval-to-execute endpoint in this version.

## Reuse

- Keep LLM work out of `services/ingestion-service/app/service.py::persist_log`. Tool implementation exposed SQLite offset loss, so its shared persistence step now normalizes stored timestamps to UTC; scoring still receives the original request.
- Use `app/database.py::SessionLocal` and the existing `Log` model for scoped evidence queries. Reuse the parameterized SQLAlchemy filtering pattern in `app/routes/logs.py::list_logs`.
- Reuse `app/security.py::require_api_key`, with an explicit nonempty-key requirement when investigations are enabled.
- Reuse `app/telemetry.py::setup_worker_telemetry` for the separate investigator process.
- Extend the in-memory database fixtures in `services/ingestion-service/tests/conftest.py` and the existing Playwright suite.
- Follow the training scripts' explicit import-path pattern when `evals/run.py` imports the serving runner; do not duplicate investigation logic in evaluation code.

Paths beginning `app/` above are relative to `services/ingestion-service/`.

## Architecture

```text
Before:
[Dashboard] <-> [Ingestion API] -> [Database]

After:
[Dashboard] <-> [Ingestion API] <-> [Database]
                                       ^
                                       |
                                [Worker + tools] <-> [LLM]
                                       ^
                                       |
                                   [Runbooks]
```

The existing scorer and optional Kafka path remain unchanged and are omitted from the diagram. The API stores a request and returns 202. A separate worker process, built from the ingestion image, performs the investigation. The browser reads persisted progress through the API.

The database remains owned by ingestion. Do not put an LLM loop inside `persist_log`, make the scorer call back into ingestion, or give a new service ownership of ingestion's tables.

### Decision 1: one worker, one provider, no agent framework yet

```diff
 # Existing behavior remains
 POST /logs -> persist_log(session, log, ai)
 POST /logs/stream -> Kafka -> persist_log(session, log, ai)
+
+POST /investigations -> validate scope -> persist queued run -> 202
+python -m app.investigator -> claim queued run -> bounded tool loop -> persist report
+GET /investigations/{id} -> persisted status and report
+GET /investigations/{id}/events?after= -> persisted tool activity and evidence
```

Use the official OpenAI Python SDK for one tool-capable model, Pydantic for arguments/results, and a plain Python loop. Pin the SDK and an available model version after checking current provider documentation during implementation. `LLM_MODEL` must be explicit; missing credentials must not silently switch to fabricated results. The provider choice is a planning default, not a claim that credentials are configured.

Reject LangGraph, multi-provider routing, and MCP for the first version. Reconsider LangGraph when paused human intervention or resumable branching is an actual requirement. Reconsider MCP when a second client needs to consume these tools.

### Decision 2: investigations are not a new incident-management system

```diff
 # Existing model
 class Log: ...
+
+class Investigation:
+    # UUID, idempotency key, validated scope, replay/live origin
+    # queued/running/completed/failed/cancelled, timestamps, deadline
+    # report, terminal reason, model/prompt versions, usage and cost estimate
+
+class InvestigationEvent:
+    # run ID + sequence unique; tool started/result/report/error
+    # validated arguments, bounded redacted evidence, latency, usage
```

Use SQLAlchemy JSON columns for bounded structured payloads and an Alembic migration for both tables. There is no separate incident, ticket, assignment, or escalation model. A request can originate from an existing log or a selected service/time window.

Use an atomic queued-to-running transition, short database transactions, and one worker with concurrency one. Do not hold a database transaction during model or network calls. Duplicate POSTs with the same idempotency key and body return the same run; conflicting reuse returns 409.

Investigation execution is disabled by default. Enabling it requires a nonempty API key, enforced at startup, and all run/evidence endpoints require that key. Bound the queue to 20 pending runs and reject excess requests with 429. The public static demo has no execution credentials or access to private history.

Queued work survives restarts. On recovery, an interrupted running job past its deadline becomes an explicit failure; retries create a new run. Do not promise resumable execution or exactly-once provider billing. Check cancellation between calls and before publishing results. A cancelled run cannot later become completed.

### Decision 3: a small set of read-only tools

Initial tool contracts, expressed independently of provider SDK syntax:

```python
query_logs(services, start, end, text=None, limit=50) -> EvidenceBatch
summarize_logs(services, start, end) -> EvidenceBatch
search_runbooks(query, limit=3) -> EvidenceBatch
```

`EvidenceBatch` contains evidence IDs, source/version, time range where applicable, bounded content, and an explicit truncation indicator. Tool errors are structured results, not empty evidence. Store exactly the redacted evidence supplied to the model so later citations survive source changes.

Scope is fixed by the request: at most four services over at most one hour. The agent may narrow that scope but cannot expand it. Manual selection includes related services; automatic dependency discovery is deferred. SQLAlchemy builds parameterized queries. No arbitrary SQL, regular expressions, filesystem paths, URLs, shell, Docker, or deployment tools are model-accessible.

Add `read_metric_series(service, metric_name, start, end)` only with the instrumented demo application. Its metric names map to server-owned query templates. Do not let the model submit arbitrary PromQL. Until then, the product promises logs and runbooks, not application-metric investigation.

Start runbook retrieval with heading-sized chunks, stable section IDs, and deterministic lexical ranking over a small curated document. Add embeddings only if retrieval evaluation shows paraphrase misses worth fixing. Existing structured filters are better suited to timestamps and service names than vector search.

### Decision 4: adaptation must be observable

```diff
- collect the same context -> ask for a summary
+ model selects a validated tool call
+ execute tool and persist its evidence
+ model uses that result to choose another query or finish
+ validate cited report against evidence available in this run
```

Cap each run at six model requests, eight tool executions, and 120 seconds of execution time. Calls and retries share the same budgets. Bound each result to 50 log rows and 16 KiB, total evidence to 64 KiB, and each model output to 1,024 tokens. Measure context size and reduce these defaults on the development set if needed. Never silently discard evidence while keeping its citation valid.

Allow at most one retry for a transient provider failure, within the deadline. Stop repeated identical tool calls. Reject unknown tools and invalid arguments before execution. Persist partial evidence when the provider fails or a budget runs out.

These are resource ceilings, not a guarantee of diagnosis quality or an exact dollar cap. Record provider-reported tokens and a dated price table for estimated cost; report unknown usage after ambiguous failures rather than zero. Do not expose paid execution publicly before adding owner authorization, queue limits, and a server-enforced spend allowance with conservative reservation for in-flight calls.

### Decision 5: findings must cite evidence, not internal reasoning

```python
class Finding:
    claim: str
    evidence_ids: list[str]

class InvestigationReport:
    outcome: Literal["supported", "inconclusive"]
    observations: list[Finding]
    likely_cause: Finding | None
    alternatives: list[Finding]
    missing_evidence: list[str]
    suggested_checks: list[str]
```

Validate that all citation IDs belong to successful tool results from this run. Require evidence for a supported likely cause. A runbook describes a possible mechanism, not proof that it occurred; a likely-cause finding needs observed incident evidence too. If validation fails, consume a remaining request to repair it or finish as failed. Do not display unsupported output as a successful report.

Citation existence is mechanically testable. Whether evidence actually supports a claim needs evaluation and human review. Do not equate a valid schema or a confident model answer with correctness. Avoid uncalibrated confidence percentages.

Show tool calls, evidence, timing, and concise findings in the UI. Do not request or store hidden chain-of-thought.

Treat log messages and runbooks as untrusted data. Place them in tool results rather than system instructions. Tool allowlists and argument validation enforce capabilities regardless of prompt content. Redact known credentials before provider submission, event persistence, tracing, and export. Regex redaction is not a general guarantee of PII removal; this release supports synthetic/sandbox data, not arbitrary production logs.

### Decision 6: preserve the frontend stack and change the workflow

```diff
- Main screen: counters -> send a log -> recent logs table
+ Main screen: saved investigations -> selected report -> cited evidence
+ Running state: actual tool events, elapsed time, cancel, explicit failures
+ Secondary logs view: existing ingestion and labeling functions
+ Evaluation view: versioned results and representative failures
```

Keep vanilla JavaScript and CSS. A React migration does not improve the AI evidence and is not needed for this screen count. Use native links, buttons, forms, and disclosure elements. Poll ordered events with a cursor every second during an active run; stop when terminal or when leaving the view. No WebSocket/SSE infrastructure yet.

Keep the dark neutral palette, blue for navigation, and amber/red for actual warnings. Use monospace for timestamps and evidence, not entire reports. Give reports more space than counters. On desktop, show investigations beside the report with an evidence drawer. On narrow screens, use a single column and contained scrolling for raw logs. Keyboard navigation, visible labels/focus, and announced status updates are acceptance requirements.

Render log and model content as text, not trusted HTML. A log containing markup or instructions must not become executable UI content.

## Evaluation design

Build the evaluation set before tuning the prompt. The key claim is falsifiable:

> Adaptive evidence collection produces more correct, supported diagnoses than fixed retrieval under a documented resource budget.

If that claim fails, publish the result. Keep the fixed workflow as the default where it wins. Do not add more agents to avoid a negative result.

### Cases and separation

Start with 24 explicitly authored incident evidence bundles: eight development cases and sixteen held-out cases. Cover upstream latency, connection exhaustion, credential/configuration failures, and benign or ambiguous error bursts. Include distractors, conflicting evidence, unavailable tools, truncation, and prompt-injection attempts. Some cases must require an inconclusive answer.

Each bundle separates observations from evaluator-only labels. Store expected causes, acceptable alternatives, supporting evidence IDs, forbidden conclusions, and required abstentions in a label file inaccessible to runtime tools. Runbooks explain procedures and mechanisms, not case IDs or case-specific answers.

Split by scenario variants, not random log rows. Do not put the same incident or a trivial renamed copy on both sides. These are controlled engineering cases, not a benchmark proving general production reliability. Freeze the test set before prompt/model comparison and create a new version if repeated inspection turns it into development data.

### Compared systems

| System | Input and behavior | Purpose |
| --- | --- | --- |
| A: one-shot logs | Same scoped log-query tool once, then one model report | Cheapest useful baseline |
| B: fixed retrieval | Predetermined log query, summary, and runbook retrieval, then one model report | Tests whether retrieval alone is enough |
| C: adaptive agent | Same evidence sources; model chooses tools, parameters, and stopping point | Tests the value of adaptive investigation |

Use the same model snapshot, report schema, source snapshots, and maximum evidence/output allowances. Log actual consumption; the agent is allowed more calls, so compare quality against cost rather than pretending equal configuration means equal spend. Run each system three times on held-out cases. Keep all failures in the denominator. No paid evaluation runs in ordinary pull-request CI.

### Scorecard

- Diagnosis accuracy against a predefined case rubric, including acceptable alternatives.
- Supported-claim precision from claim-by-claim evidence review.
- Citation validity and expected evidence recall.
- Correct abstention on insufficient-evidence cases, separately from successful diagnoses.
- Tool/schema failures, forbidden capability attempts and executions, deadline/call-budget compliance.
- Latency p50/p95, actual token usage, estimated cost per run, and cost per correct supported diagnosis.
- Raw counts and variation across repetitions. Report the small sample size; do not advertise a precise generalization rate.

Automate schema/citation/budget checks. Blind-review diagnosis and evidence support against the stored rubric. An LLM judge may assist error analysis, but cannot be the only ground truth. Store model ID, prompt hash, dataset hash, code revision, parameters, and price-table date with every result.

Target, not a promised result: beat fixed retrieval on supported diagnoses while keeping median estimated cost below $0.10 and p95 runtime below 60 seconds. Hard release gates: no forbidden tool executes, no accepted report contains a nonexistent citation, and executing runs obey configured limits. Worker outages must be visible, with interrupted jobs reconciled on recovery. Publish failed targets instead of selecting only favorable runs.

## Steps

Planning estimate: four to six part-time weeks for the core and portfolio packaging. This assumes existing Python/FastAPI familiarity and access to one paid model. It is not a deadline commitment. The controlled live-fault demo follows the evaluated core rather than blocking the first working version.

### Phase 1: evidence and a fixed-workflow baseline

- [x] Create versioned development/test evidence and separate evaluator labels.
- [x] Add the three bounded tools and curated runbook sections. Use the same tool interface for replay and database-backed evidence; keep fixture sources inaccessible to public user-supplied paths.
- [x] Build systems A and B with the selected SDK, explicit model configuration, structured reports, and citation checks.
- [x] Add deterministic tests for time/service scope, UTC handling, invalid input, redaction, truncation, and runbook retrieval. Test offset-aware timestamps and reject naive request timestamps.
- [x] Run `make test` and `make lint`, then a small explicitly budgeted live development evaluation.
- [x] Save one successful and one inconclusive baseline report with provenance.

Deliverable: one command produces a cited report from a known evidence bundle. No agent loop or UI redesign yet. This phase answers whether the evidence and report contract are useful at all.

### Phase 2: the adaptive investigation engine

- [x] Add the bounded tool-selection loop behind the same runner interface as the baselines.
- [x] Use scripted provider responses to prove that one tool result changes the next query. A fixed tool sequence with LLM narration does not pass this check.
- [x] Cover unknown tools, malformed arguments, duplicate calls, invented citations, provider errors, injection text, missing evidence, and exhausted budgets.
- [x] Run A/B/C against the development cases; inspect failures before tuning the prompt.
- [x] Freeze a candidate prompt and run the held-out comparison with explicit cost authorization. Preserve complete result artifacts.

Deliverable: measured evidence for where adaptation helps and where it does not. Keep the fixed baseline runnable after this phase.

### Phase 3: durable API and worker

- [x] Add investigation/event models and an Alembic revision without altering existing log rows or scoring contracts.
- [x] Add authenticated create/list/detail/events/cancel endpoints with request bounds, a 20-run queue limit, and idempotency-key behavior. Refuse to enable investigation execution without an API key.
- [x] Run the investigator as a separate process from the existing image. Claim jobs atomically, record ordered events, enforce deadlines, and preserve terminal states.
- [x] Reuse opt-in worker telemetry. Store per-run usage and timings in the database; do not assume counters in a separate worker are exposed by the API's `/metrics`.
- [x] Test reload/history, duplicate submission, restart recovery, cancellation races, and a model outage while log ingestion remains usable.
- [x] Test migration from revision 0002 on an isolated database, inspect the actual Alembic revision, and run the relevant live integration suite against task-owned containers.

Deliverable: a queued run can outlive the browser connection, be inspected later, and fail visibly without affecting log ingestion. No promise of resuming a partially completed model conversation.

### Phase 4: an investigation workspace

- [x] Build the investigation list, run detail, progress view, citation drawer, and inconclusive/error/cancelled states.
- [x] Keep existing log submission and feedback in a secondary view. Check `response.ok` and show failed feedback writes rather than swallowing them.
- [x] Add a read-only evaluation page from published result artifacts. Distinguish recorded reports from live execution.
- [x] Use browser tests to start a run, follow tool progress, open citations, cancel, reload history, and inspect provider failure.
- [x] Replace the weak feedback assertion with a check of the specific saved label and API state.
- [x] Verify 1440px desktop and 390px mobile views, keyboard operation, empty states, overflow, and malicious log/model text.

Deliverable: a reviewer can understand the incident, evidence, and measured limitations without reading source code. Screenshots alone do not complete this phase; exercise the workflow in a running browser.

### Phase 5: a controlled live failure and portfolio release

- [x] Add one small demo application deployed twice as checkout and inventory. Checkout calls inventory over real HTTP; a controlled inventory delay produces real upstream timeouts.
- [x] Keep fault controls in an isolated, non-public demo network and out of the agent tool registry. The owner-operated scenario script alone triggers and resets faults. Do not stop shared services or change production infrastructure.
- [x] Emit structured logs to the existing ingestion API and real request/error/latency metrics. Add the fixed-template metric tool and a demo-only Prometheus configuration. Leave both base monitoring configurations unchanged.
- [x] Verify healthy traffic, apply delay, wait for observed timeouts, investigate, remove delay, and verify recovery. Reset task-owned fault state in `finally`; never use a screenshot as proof of recovery.
- [x] Capture evidence bundles from these runs for a separate live-origin evaluation set. Keep fault-control metadata and expected answers out of model-visible evidence.
- [x] Provide a minimal demo Compose file without Kafka, Grafana, or Kubernetes requirements. Preserve the existing full-stack configuration for infrastructure demonstrations.
- [x] Publish a static read-only portfolio demo plus a local owner-run live mode. No public paid execution or arbitrary log upload in v1. Any later hosted execution requires a separate authorization and spend-control review.
- [x] Update README, architecture notes, screenshots, and a 90-second recording. Publish the evaluation method, complete scorecard, and at least three failure analyses.

Deliverable: a recruiter can inspect a recorded investigation immediately, and an engineer can reproduce a real fault locally. Public hosting itself requires explicit approval and is not performed as part of planning.

## Files to modify

Exact new filenames below are proposed, not files that already exist. `I/` means `services/ingestion-service/`. Add focused tests alongside the behavior they prove, not a new testing framework.

| File | Today | After |
| --- | --- | --- |
| `I/app/investigation_schemas.py` | Absent | Scope, tool/result contracts, report validation, statuses |
| `I/app/investigation_tools.py` | Absent | Bounded database/replay queries, lexical runbook retrieval, evidence IDs and redaction |
| `I/app/investigation_agent.py` | Absent | Baseline/adaptive runners, SDK calls, prompt version, budgets and validated final reports |
| `I/runbooks/operations.md` | Absent | Versioned sections for diagnosis procedures, with stable IDs |
| `I/requirements.txt` | FastAPI, HTTPX, SQLAlchemy and telemetry | One pinned official provider SDK added |
| `I/app/config.py` | Scoring, DB, auth and Kafka settings | Explicit model, run limits, runbook path, replay/live mode and optional metrics endpoint |
| `I/tests/test_investigation_tools.py` | Absent | Same contracts tested against replay and database evidence |
| `I/tests/test_investigation_agent.py` | Absent | Scripted model tests for adaptive behavior, safety and failure handling |
| `evals/cases/dev.jsonl` | Absent | Eight development evidence bundles |
| `evals/cases/test.jsonl` | Absent | Sixteen frozen held-out evidence bundles |
| `evals/labels.jsonl` | Absent | Evaluator-only rubric and expected evidence, excluded from runtime images |
| `evals/run.py` | Absent | A/B/C execution, run manifests and score aggregation; imports the serving runner |
| `evals/README.md` | Absent | Dataset provenance, splits, grading rules and limitations |
| `evals/results/baseline.json` | Absent | Versioned aggregate results with links to bounded sanitized run artifacts |
| `I/app/models.py` | Log rows and feedback | Investigation and event tables added |
| `I/migrations/versions/0003_add_investigations.py` | Absent | New tables, uniqueness constraints, scope-query index on logs |
| `I/app/routes/investigations.py` | Absent | Bounded authenticated run endpoints |
| `I/app/investigator.py` | Absent | Worker lifecycle, atomic claims, event persistence, deadline cleanup |
| `I/app/main.py` | Existing routers and lifespan | Registers investigation routes, never starts the LLM loop in the HTTP process |
| `I/Dockerfile` | Packages app and migrations | Also packages runbooks; investigator uses the same image |
| `I/tests/test_investigations.py` | Absent | Run/API/worker lifecycle and authorization tests |
| `tests/integration/test_investigations.py` | Absent | Real database migration, worker isolation and restart tests |
| `tests/integration/test_stack.py` | Column-based migration check | Actual revision assertion when this migration work lands |
| `frontend/index.html` | Log submission dashboard | Investigation workspace and secondary logs view |
| `frontend/app.js` | Polling, rendering, feedback | Preserves log flows; links to investigation views and reports failures |
| `frontend/investigations.js` | Absent | Run submission, cursor polling, evidence and report rendering |
| `frontend/styles.css` | Dark dashboard, limited mobile rules | Investigation layouts, accessible states and narrow-screen handling |
| `frontend/evaluation.html` | Absent | Read-only measured comparison and failure examples |
| `tests/e2e/test_dashboard.py` | Existing dashboard checks | Retained log-flow coverage with real feedback assertion |
| `tests/e2e/test_investigations.py` | Absent | Full investigation flow, failure states, accessibility basics and screenshots |
| `demo/app.py` | Absent | One small app running in checkout/inventory roles with bounded fault controls |
| `demo/Dockerfile` | Absent | Packages sandbox app using existing pinned FastAPI/HTTPX/metrics dependencies |
| `demo/run_scenario.py` | Absent | Owner-operated fault lifecycle and observation capture |
| `demo/test_scenario.py` | Absent | Real timeout and recovery checks against an isolated sandbox |
| `infrastructure/docker/demo-compose.yml` | Absent | Minimal local agent + sandbox stack, private fault controls |
| `demo/prometheus.yml` | Absent | Scrapes the two sandbox applications; used only by demo Compose |
| `Makefile` | Existing install/test/demo commands | Installs all documented test deps; adds evaluation/worker/demo commands, new deterministic suites, and lint coverage for evals/demo/tests/scripts |
| `.github/workflows/ci.yml` | Existing test and stack jobs | Includes deterministic agent/eval/sandbox checks, no automatic paid calls |
| `scripts/capture_demo.py` | Records a single log and feedback | Records incident investigation and cited report |
| `scripts/smoke.py` | Health, ingest, metrics and model probes | Also checks investigation availability/history without silently spending on an LLM call |
| `README.md` | Anomaly-scoring platform, historical ML findings | Agent demo first, reproducible metrics, links to ML case study and limitations |
| `docs/architecture.md` | Some stale deployment/migration descriptions | Actual worker/data flow, resource limits and failure behavior |
| `docs/ai-evaluation.md` | Absent | Measured A/B/C findings, failure analysis and reproduction commands |

The sandbox is Compose-only. `demo/prometheus.yml` belongs to that deployment; the two existing base monitoring configurations stay unchanged. Expanding the Kubernetes deployment to include the sandbox is out of scope.

## What we are deliberately not building

- Autonomous remediation, shell execution, Kubernetes control, arbitrary URL fetches, or user-uploaded private logs.
- Multi-agent roles, a vector database, fine-tuning, long-term agent memory, or an MCP server without a demonstrated need.
- A React migration, multi-tenant SaaS, billing, incident assignment, Slack/GitHub integrations, or a new image/CD pipeline.
- Automatic investigation for every anomalous log. Manual initiation is easier to evaluate and prevents accidental model spend.
- A full rewrite of the existing classifier or a BGL retraining project before the investigation workflow exists.
- Kafka reliability repairs as a prerequisite. The existing consumer auto-commits and catches processing failures without a durable retry/dead-letter path. Do not claim lossless processing; keep the new worker off that path.
- Production-grade privacy or security based on the current demo defaults. No public execution until separately reviewed controls exist.

The synthetic training experiment remains labeled as such. Stop using its metrics as the project's main AI claim. The README's analysis of failed assumptions is useful portfolio evidence if it is presented honestly.

## Verification and portfolio completion criteria

- [x] A 90-second demonstration shows an observed failure, adaptive investigation, clickable evidence, and an honest conclusion.
- [x] A separate inconclusive example demonstrates that missing evidence does not become a fabricated root cause.
- [x] A single documented local command starts the minimum demo; no Kafka or Kubernetes prerequisite.
- [x] A read-only public artifact is usable without a provider key and is explicitly marked as recorded.
- [x] A/B/C results include costs, latency, abstentions, failures, dataset limits, and reproduction metadata.
- [x] Deterministic tests, affected integration suites, browser flows, and the actual sandbox fault/recovery check have fresh evidence.
- [x] Documentation distinguishes completed features, experiments, and deferred work.

Resume wording comes last. Describe what the evidence supports: "Built an incident-investigation agent with bounded tool use and cited reports; evaluated adaptive retrieval against fixed workflows on versioned incident cases." Add measured numbers only after the evaluation runs.

## Review status and next action

The plan was approved through Plannotator and execution is active. Step 1 is implemented in `.worktrees/3-incident-evidence` on branch `feat/3-incident-evidence`, linked to GitHub issue #3. The corpus has 8 development cases, 16 held-out cases, 169 observations, and separate evaluator labels. All 100 local tests and lint passed after adding 33 corpus checks.

Issue #3 still requires code review and integration. With user authorization, commit `957afe3` was pushed and [PR #14](https://github.com/HitendraKawale/log-guardian/pull/14) opened against `main`. It has not been merged; all PR #14 checks passed.

Step 2 is implemented locally in `.worktrees/4-evidence-tools` on `feat/4-evidence-tools`, based on PR #14's commit. It adds the three evidence tools, five runbook sections, bundled runbook files, and 43 tests. All 143 local tests and lint passed. A development corpus case was exercised through all three tools. A regression test required a shared UTC persistence fix because SQLite drops offsets. Historical rows with already-lost offsets are not repaired.

The Docker daemon is unavailable, so PostgreSQL and image execution for step 2 remain unverified. With user approval, issue #4 was committed as `133a5b9`, pushed, and published as [PR #15](https://github.com/HitendraKawale/log-guardian/pull/15), stacked against `feat/3-incident-evidence`. Its seven-file diff excludes the corpus changes. The worktree is clean; fresh verification passed all 143 tests and lint. All PR #15 CI checks passed. Neither PR has been merged; retarget #15 to `main` after #14 is integrated.

Steps 3 and 4 are implemented locally on `feat/5-investigation-baselines` in `.worktrees/5-investigation-baselines`, based on `133a5b9`. OpenAI SDK 2.11.0 is pinned. The explicit supported snapshot is `gpt-4.1-mini-2025-04-14`, with pricing checked against its official model page on 2026-09-13. A/B share structured reports and citation checks; the development CLI records provenance, refuses accidental live calls, and enforces a conservative per-request cost preflight. It does not claim an account-wide spend cap.

Fresh `make test` passed 177 tests, `make lint` passed, and `pip check` reported no broken requirements. The evaluation suite also passed all 38 tests with plugin autoload disabled. The 45 tool checks include an additional ISO timestamp regression: epoch strings were previously coerced into aware datetimes despite the documented input contract. The schema now parses ISO strings before enforcing timezone awareness.

A/B dry-run artifacts are in `/tmp/log-guardian-baselines.Wdv3dv/`. Both made zero provider requests; A used one tool and B used three. Scripted SDK responses are test evidence, not live evaluation results. With user approval, issue #5's offline implementation was committed as `e4edf8b`, pushed, and published as draft [PR #16](https://github.com/HitendraKawale/log-guardian/pull/16), stacked against `feat/4-evidence-tools`. Fresh verification again passed 177 tests, lint, and dependency checks. The worktree is clean. No PR was merged. Step 5 is now complete: after explicit approval for four requests and $0.10 total, A/B ran on dev-01 and dev-06 using clean revision `e4edf8b`. All four requests returned known usage; estimated total cost was $0.00366960. The four-request authorization is exhausted.

Both systems matched dev-01's core deadline explanation, with attribution/health-overclaim caveats. Both incorrectly asserted that missing collector log data caused dev-06's search timeouts. Correct abstentions: 0 of 2. Valid citation IDs did not prevent unsupported causality. Step 6 therefore remains open, and PR #16 stays draft. Do not relabel these failures or skip to the adaptive phase.

All four original reports, a machine-readable summary, and review notes are saved locally under `.worktrees/5-investigation-baselines/evals/results/2026-09-13-baseline-smoke/`. They are not yet committed or pushed. An offline archive check verifies hashes, provenance, citations, resource bounds, and accounting. Fresh verification after archiving: 178 tests passed; lint printed `All checks passed!` and `67 files already formatted`. No runtime code or prompt was changed during this batch. Further paid requests require a new authorization; public hosting remains separately gated.

An offline correction candidate now excludes common question words from lexical ranking and matches section IDs as well as titles/bodies. A dev-06 dry run retrieves `runbook:timeouts` with zero provider requests. The shared prompt now separates missing telemetry from application failures and requires evidence for dependencies, deadlines, and broad health claims. New prompt hash: `7490913eb179976232ddc28f8cbe8e60eb262f7a847fda46cf972fb27131f2cb`. Six new regression/prompt-transport checks passed; all 184 tests and lint passed. The four original live reports remain unchanged. With explicit approval, the candidate and first batch were committed/pushed as `0a97c3f`. A second authorized four-request batch ran on that clean revision, using the same two development cases and model. Estimated cost: $0.00401200. Both dev-06 reports still asserted the unsupported collector-to-request causal link, although B now retrieved the timeout runbook. Correct abstentions remained 0 of 2. The correction did not demonstrate an abstention improvement on this case.

Second-batch JSON files, summary, and review notes are preserved under `evals/results/2026-09-13-baseline-smoke-v2/` in the issue #5 worktree, not yet committed or pushed. Both archives pass offline hash/provenance/citation/resource/accounting checks. Fresh verification: 185 tests and lint passed. Across both batches, eight requests cost an estimated $0.00768160; both authorizations are exhausted. No additional prompt changes or paid requests were made. Step 6 remains open and PR #16 remains draft.

Offline diagnosis reconstructed dev-06 through the real SDK with mock transport: the original local request included the policy and archived evidence, allowed an inconclusive outcome with null cause, and accepted that scripted response unchanged. This does not prove live model behavior. The provider documents schema-key output ordering, and the evaluated schema placed outcome before observations/gaps. A schema-order-only candidate now emits observations, missing evidence, alternatives, likely cause, outcome, then suggested checks. Field definitions/validators and prompt/runner/retrieval/model/evidence are unchanged. Candidate prompt/schema hash: `cb18775883d13c3740332ed3e98b1b0f7358b4a494967a2e360cafd77e2f66c6`. Early commitment is an unverified hypothesis, not a claimed root cause.

The diagnosis is recorded in `docs/baseline-abstention-diagnosis.md` in the issue #5 worktree. New SDK-boundary tests passed; all 187 tests and lint passed. At that point the candidate and second-batch archive were uncommitted, and another live evaluation needed explicit authorization.

The user approved the order-only candidate and a fresh four-request, $0.10 trial. Candidate and second-batch archive were committed/pushed as `8edf09e`. Four requests ran on that clean revision for an estimated $0.00409200. Both dev-01 reports retained the deadline mechanism. A/dev-06 declined to assert a cause and requested search-side logs/traces and transport-versus-handler timing. B/dev-06 also emitted inconclusive, but repeated the unsupported collector request dependency in alternatives/checks. Count two abstention labels, only one core abstention review pass. A's observation-level limitations are documented, not erased.

Step 6 is complete: representative reports B/dev-01 (supported) and A/dev-06 (inconclusive) are saved with original evidence/provenance under `evals/results/2026-09-13-baseline-smoke-v3/`. All four original files, summary and review were committed/pushed separately as `9d6a86d`. Fresh verification passed 188 tests and lint; archive checks preserve all twelve originals and verify unchanged tool evidence relative to batch two. All three request allowances are exhausted, with twelve requests costing an estimated $0.01177360 total. No further paid call, held-out evaluation, merge, or public hosting is authorized. Next is issue #6 / steps 7–9, the bounded adaptive loop and offline scripted/adversarial tests.

Steps 7–9 are now implemented locally on `feat/6-adaptive-investigator` in `.worktrees/6-adaptive-investigator`, based on `9d6a86d`. `run_investigation` dispatches A/B unchanged or C's native tool-selection loop; the CLI accepts C and fingerprints its implementation. C enforces six model requests, eight tool executions, 120 seconds, 64 KiB evidence and 1,024 output tokens per request. It validates tool arguments, normalizes duplicate queries, preserves partial evidence/per-call usage, and stops on ambiguous billing without retries. Cache omissions are explicit and receive no assumed discount.

Twenty-six new SDK transport tests cover evidence-dependent next queries, invalid tools/arguments/IDs, duplicate calls, scope violations, missing/contradictory evidence, injection attempts, invalid reports/citations/provider output, unavailable runbooks, provider failure and resource ceilings. Tests exposed and then verified fixes for duplicate call IDs and a blocking response bypassing the async timer. Fresh `make test`: 215 passed; `make lint`: all checks passed, 70 files formatted. C CLI dry run: zero model/tool requests, first-request reservation $0.00525840. No paid C run, commit, push, new PR, local container verification or merge occurred. Step 10 needs a new development evaluation allowance; held-out evaluation remains separately gated.

Step 10 is complete. The authorized 24-run A/B/C comparison ran on clean `ad7f95f`: 46 requests, estimated $0.03470640, all usage known, no retries. Core review passes: A 7/8, B 7/8, C 4/8. C's dominant failure is overly narrow literal text filters (missing evidence, one model-budget exhaustion, one unnecessary abstention, one ungrounded diagnosis); two runs failed report validation with raw output deliberately unarchived; B again failed dev-06 abstention. Full artifacts, review notes and failure analysis are in `evals/results/2026-09-14-dev-abc/` (commit `bbf5980`), with an offline archive test. Candidate directions (tool-description clarification, unfiltered-first querying) are documented but deliberately not applied; any change requires fresh evaluation. Step 11's held-out comparison needs separate explicit cost authorization.

Per the user's option-1 decision, C's `query_logs` description was clarified (unfiltered first; text matches message only) as `998ed13` and C was rerun on all eight development cases: 5/8 core passes, 8/8 completed, 20 requests, $0.01367280 (`evals/results/2026-09-14-dev-c2/`, commit `6a558ee`). Remaining C failures are filter-first unnecessary abstentions on dev-02/04/05; dev-04 moved from ungrounded-supported to unnecessary abstention. A/B inputs are unchanged, so their `2026-09-14-dev-abc` results stand. C remains below A/B. The candidate configuration is now frozen for step 11; the held-out run itself still needs an explicit allowance.

Step 11 is complete. With the approved $1.20 allowance, the CLI gained gated `--held-out` split selection (`7f3889b`) and all 48 held-out runs executed on that clean revision: 74 requests, $0.06788320, every artifact preserved including four failures. Core review passes: A 12/16, B 13/16, C 11/16; required abstentions A 0/3, B 1/3, C 1/3. The adaptive hypothesis is not supported: B leads at lower cost. Shared weaknesses: unreliable-ordering overconfidence (test-13, 0/3), truncation blindness (test-16, 0/3), single-fault compression (test-14). No system executed the test-15 injected instructions. Archive, review notes and failure analyses: `evals/results/2026-09-14-heldout/`, commit `77ec1d1`, with an offline archive test. This held-out split is consumed; further tuning requires a new set. Cumulative paid spend across all authorizations: about $0.198.

Steps 12–13 are implemented on `feat/8-investigation-api` (`.worktrees/8-investigation-api`, based on `77ec1d1`), commit `37a5d70`, PR #18 stacked on #17. Alembic `0003` adds `investigations`, `investigation_events` (unique run/sequence index) and a `(service, timestamp)` logs index; a test migrates 0002→0003 on an isolated database, checks preserved log rows, and downgrades. The `/investigations` API queues without model calls, returns 503 on every route while `INVESTIGATION_API_KEY` is empty, enforces the 20-pending limit with a post-commit concurrent-overshoot check, and implements idempotency (same body replay, 409 conflict, concurrent-duplicate race). Cancel maps queued→cancelled, running→cancelling, terminal→409. Verification: 228 tests passed, lint clean. Deferred: worker process (14–16), PostgreSQL container migration check (17, Docker unavailable locally), UI.

Steps 14–16 landed as `a72c734` on the same branch/PR #18: `python -m app.investigator` (same image; profile-gated compose service), atomic single-winner claims, ordered per-tool events plus a terminal status event, stale-claim recovery, cancellation races resolving to cancelled, provider-outage and missing-credential runs failing closed while log ingestion continues, and usage/cost/timings stored on the run row with opt-in worker telemetry. Nine worker tests; 237 total, lint clean.

Step 17 completed once Docker became available. PostgreSQL 16 container migration: 0001→0002, seeded log row, 0002→0003; `alembic_version` reads `0003`; the row and new indexes verified via psql. The full compose stack built from this worktree passed all 16 live integration tests, and the investigations API returned 503 for create/list with no configured key (execution disabled by default); the stack's own PostgreSQL also reports revision 0003. Task-owned containers were removed afterward. No live worker/model execution ran in containers; that would need a paid allowance.

Steps 18–23 landed on `feat/10-investigation-ui` (commit `b38cf26`, PR #19, stacked on #18). Tabbed vanilla-JS UI: investigations (list beside detail, 1s cursor event polling stopping on terminal/leave, citation drawer from recorded tool evidence, explicit failure/cancel/inconclusive states with preserved partial evidence), logs+feedback secondary tab with visible failed feedback writes, and a recorded-only evaluations tab fed by `frontend/evaluations.json` (80 runs exported from the three published summaries). All model/log text renders as text nodes. Ten deterministic Playwright tests against a stub API pass, covering the required flows plus malicious-content non-execution, keyboard navigation, empty states, and 1440/390 overflow checks with fresh screenshots; the live-stack feedback test now asserts the specific saved label. 237 backend tests and lint clean. Not done: UI exercised against a live worker with real model spend.

Steps 24–29 and 34 landed on `feat/11-demo-sandbox` (`ec8383f`, PR #20, stacked on #19). One demo app in checkout/inventory roles with real HTTP deadlines; localhost-only fault port outside the agent tool registry; structured logs to ingestion plus real Prometheus metrics; fixed-template `read_metric_series` with strict service-name validation (injection shapes rejected before any request) and `source_unavailable` when unconfigured; minimal `make demo-up` compose without Kafka/Grafana/K8s; base monitoring untouched. The scenario ran against real containers: five healthy 200s, three genuine 504s under a 3s injected delay, `finally` reset, five recovered 200s, nonzero Prometheus 504 rate. A 38-row live-origin bundle was captured and checked free of fault metadata/expected answers. In-process sandbox suite (3), metric-tool suite (5); 242 tests and lint clean. The scenario's investigate step ran without a live model call; a paid sandbox investigation remains gated on a new allowance.

Steps 30–33 and 35–38 landed on `feat/12-portfolio` (`57b4350`, PR #21, stacked on #20). Static recorded demo built from two real preserved live artifacts (adaptive supported test-03-C, adaptive inconclusive dev-06-C), marked recorded, verified in a browser with no backend by five new tests; `site/` is a gitignored build. An 87.6-second recording (`docs/media/demo-90s.webm`) shows failure evidence, adaptive tool activity, clickable citations, the honest conclusion and the separate inconclusive example, with the recorded banner visible throughout. `docs/evaluation.md` publishes the method, complete six-batch scorecard (92 runs, 152 requests, est. $0.12803600), per-system held-out results, four failure analyses and limits. README and architecture docs distinguish shipped/experimental/deferred and keep the synthetic-classifier limitation. Fresh verification: 242 unit/contract/eval tests, 3 sandbox tests, 15 browser tests, lint clean.

Still deliberately open: public hosting of the static artifact (issue #12 final criterion; needs explicit approval), any live sandbox investigation (paid), independent review, and any further tuning (requires a new held-out set). The plan's 38 execution steps are otherwise complete; no PR was merged.
