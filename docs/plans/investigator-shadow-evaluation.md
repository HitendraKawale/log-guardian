# Investigator shadow evaluation

Use `executing-plans` for staged execution. Do not commit or publish without owner approval.

## Goal and chosen application

Use Log Guardian's own incident investigator, not a new demonstration assistant.
Its worker already executes real database, runbook and metric tools and persists
investigation events. First prove capture coverage; then measure shadow monitoring
against a basic policy baseline. Actual user traffic and independent review remain
necessary before a real-world effectiveness claim.

The owner authorized choosing a feasible application and executing the previously
discussed shadow/staging approach. This document narrows the first implementation
to the capture prerequisite and local recording-overhead measurement. It does not
authorize production access or model spending.

```text
[Registered tools] -> [Worker recorder] -> [Evidence tools]
                            |                    |
                            +---- [Event DB] <---+
                                      |
                              [Future shadow review]
```

## Cause and first decision

`RecordingTools.__getattribute__` maintains a separate three-tool list. The
adaptive agent exposes four tools. Consequently `read_metric_series` bypasses
both event recording and the worker's cancellation check.

Reuse `investigation_loop.TOOL_SCHEMAS`, rather than adding another independently
maintained four-tool list. Keep the existing event format, tool results and scope
enforcement unchanged. Importing the registry does not invoke a model.

```diff
+from .investigation_loop import TOOL_SCHEMAS
 ...
-        if name in {"query_logs", "summarize_logs", "search_runbooks"}:
+        if name in TOOL_SCHEMAS:
```

| File | Today | After this checkpoint |
| --- | --- | --- |
| `services/ingestion-service/app/investigator.py` | Three tools recorded and cancellation-checked | Every registered tool uses the existing wrapper |
| `services/ingestion-service/tests/test_investigator.py` | Lifecycle coverage mostly exercises baseline B | Every registered tool has capture/cancellation regressions; metric success and scope denial tested |
| `services/ingestion-service/measure_recording.py` | No paired measurement command | Compares real unrecorded/recorded queries on disposable file-backed SQLite, asserting equal results and complete event counts |
| This document | No application-specific evaluation path | Tracks the first fix and separates later validation stages |

## First checkpoint: capture prerequisite

- [x] Inspect real dispatch, scope enforcement, recorder and worker tests.
- [x] Create isolated issue #40 worktree from `723b1c5`; baseline: 229 ingestion tests pass.
- [x] Add failing regressions covering the registry, cancellation, a successful
  metric result through mocked Prometheus HTTP, and a denied out-of-scope metric.
  Use real `RecordingTools` and database event persistence. No provider calls.

Test input mapping:

```python
TOOL_ARGUMENTS = {
    "query_logs": SCOPE,
    "summarize_logs": SCOPE,
    "search_runbooks": {"query": "checkout"},
    "read_metric_series": {
        "service": "checkout", "metric_name": "error_rate",
        "start": SCOPE["start"], "end": SCOPE["end"],
    },
}
# Parameterize over this mapping and assert its keys equal TOOL_SCHEMAS.
# Normal call: exactly one persisted tool_call with the actual returned batch.
# Cancelling run: CancelledError, no tool body execution and no tool_call event.
# Metric HTTP success: one controlled response produces a persisted metric item.
# Outside scope: scope_violation, no Prometheus request, persisted denial result.
```

- [x] Run the new tests red, apply only the registry reuse above, then run green.
- [x] Run `make test`, `make test-demo`, `make lint`, and `git diff --check`.
- [x] Record results and known capture limits below. Preserve all earlier pilot archives.
- [x] Measure local recording overhead twice, using 3 rounds of 100 randomized-order
  pairs per execution, 5 warmup pairs per round and 50 rows per query. Assert equal
  returned batches and exact persisted-event counts; preserve every timing sample.

## Second checkpoint: offline shadow review

Reuse persisted `InvestigationEvent` rows; do not add another collection path or
change enforcement. `app/investigation_shadow.py` will compare each recorded call
with a simple tool/scope baseline and report disagreements, scope denials,
validation failures and run-level rejections. Output only event sequence numbers,
known tool names and classifications, never evidence bodies or query text.

`rehearse_shadow.py` will exercise the real adaptive loop, worker, scoped database
queries and event commits using a scripted HTTP provider and a disposable SQLite
file. Cases cover allowed/narrowed queries, forbidden service/time ranges, an
out-of-scope metric, quoted hostile text, an unknown tool, malformed arguments and
an injected event-write failure. An external test counter records executed tools
so missing events are measurable in rehearsal, not guessed from event rows.

- [x] Add `tests/test_investigation_shadow.py` with independent baseline disagreement,
  output privacy and real-worker rehearsal assertions. Run red before implementation.
- [x] Implement the read-only reviewer and rehearsal command. No model calls.
- [x] Preserve full synthetic evidence, source hashes and the controlled coverage gap.
- [x] Run all affected suites and lint. Report comparison with the simple baseline,
  not an accuracy score. Operator review time and real-user false-alert rate remain unknown.

The reviewer must not infer an attack from a denied query. Nor may it call capture
complete from the events alone: an unknown/malformed call can stop before recording,
and a tool can finish before an event write fails. Rehearsal input counts are a
test oracle, not telemetry available in production.

## Later evaluation stages

These are separate deliverables, not claims made by this checkpoint.

- [ ] Local shadow measurement: derive scope-denial observations from existing
  events, without changing tool execution. Compare with a basic allowlist/scope
  baseline. Measure missing records, added p50/p95 latency, event-write failures
  and operator review effort. Use paired runs against the same database workload;
  store raw measurements and repeat them. Scripted provider traffic is engineering
  evidence only, not live-agent attack resistance.
- [ ] Controlled staging attacks: test prohibited service/time-window queries,
  fabricated tool names, malicious log/runbook instructions and downstream reuse
  of attacker text. Keep explicit scripted violations separate from model-chosen
  violations. Independent reviewers define expected outcomes before a frozen run.
  A new scoped paid authorization is required; the email pilot allowance is not reused.
- [ ] Real-user shadow period: obtain permission for the application/data, define
  retention and access, and agree on alert workload/latency/cost thresholds before
  collecting. Review alerts and a random sample of non-alerted investigations.
  There is currently no recruited external deployment or real-user traffic source.
- [ ] Publish only supported conclusions, with baselines, denominators, uncertainty
  and limits. This requires separate publication approval.

## Deliberate omissions and limits

No new dashboard, detector rule, schema migration, blocking control, paid request,
production deployment or security-effectiveness benchmark claim. The first application is read-only;
email-recipient rules are not applicable to it. Scope denials are policy outcomes,
not proof of malicious intent.

Completed-tool recording is not a durable pre-execution journal. Unknown tools
and malformed calls can be rejected before the wrapper; crashes or persistence
failures can leave incomplete capture. These need explicit assessment before
claiming full attempted-action coverage. Existing credential redaction is not
complete PII removal, so private customer data is excluded from the local phase.

## First checkpoint results

Four metric-specific regressions failed before the fix, while the other 15 worker
tests passed. After registry reuse: 443 offline tests and 6 demo tests passed;
lint and whitespace checks passed. Logs: `/tmp/lg40-red.log`, `/tmp/lg40-verified.log`.

Two local measurement executions each persisted all 315 expected query events,
including warmup. Paired added median latency was 2.099 ms and 2.063 ms; paired
p95 was 2.756 ms and 2.914 ms. This is sequential SQLite query overhead, not
end-to-end model latency, production throughput or security efficacy.

Raw samples, source hashes and limitations are in
`evals/results/2026-09-22-investigator-recording/`. Scope-denial shadow analysis,
operator comparisons, contention/failure testing, independent attacks and real-user
observation remained unfinished at the first checkpoint. No external application
deployment or paid model call was performed.

## Second checkpoint results

The nine-case rehearsal completed with real tools/persistence and scripted model
responses. Three scope denials matched the basic scope baseline; no additional
policy-detection coverage was demonstrated. Unknown tools and malformed arguments
stopped before execution, without detailed tool events.

Selective event-write failure left one completed database query without a tool
record. The worker persisted only worker_error. The reviewer therefore does not
infer capture completeness from event rows. The test-only execution counter is
explicitly separate from production telemetry.

All nine new tests failed before implementation. Afterwards, 452 offline tests
and six demo tests passed; lint passed. Artifacts and limitations:
`evals/results/2026-09-22-investigator-shadow/README.md`.

Remaining work includes pre-execution audit design/failure policy, contention and
physical storage-failure tests, operator measurements, independent attack review,
new scoped model authorization and a consented real-user deployment. A synthetic
rehearsal does not satisfy those requirements. No runtime enforcement was changed.
