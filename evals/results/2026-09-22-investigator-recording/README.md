# Local investigator recording measurements

Application: Log Guardian's existing incident investigator. This measures its real
`EvidenceTools.query_logs` and `RecordingTools.query_logs` paths against disposable
file-backed SQLite. It does not use a model, customer logs or a production service.

## Results

| Measurement | First execution | Repeat |
| --- | ---: | ---: |
| Unrecorded query median | 1.987 ms | 1.982 ms |
| Recorded query median | 4.134 ms | 4.131 ms |
| Unrecorded query p95 | 2.315 ms | 2.356 ms |
| Recorded query p95 | 5.037 ms | 5.165 ms |
| Paired added median | 2.099 ms | 2.063 ms |
| Paired added p95 | 2.756 ms | 2.914 ms |
| Persisted events, including warmup | 315/315 | 315/315 |

Each execution used three rounds, each with 100 measured pairs and five warmup
pairs. Baseline/recorded order was randomized using a fixed seed per round.
Every query returned the same 50 synthetic log rows. Runnable assertions checked
identical returned batches and exact persisted event counts. Raw timings are in
`measurements.json` and `measurements-repeat.json`.

Recorded timings include the existing cancellation-status read and committed
event write. Paired added p95 is the percentile of within-pair differences, not
subtraction of the two independently computed p95 values.

## Capture prerequisite

Inspection found that the worker's separate three-tool registry omitted
`read_metric_series`. It therefore bypassed recording and cancellation. The fix
reuses the agent's existing four-tool registry. Four metric regressions failed
before the fix; the complete suite then passed 443 offline tests and six demo tests.
Those checks cover all four tools, metric HTTP success through a mocked endpoint,
out-of-scope metric denial without HTTP, and cancellation before tool execution.
The timing experiment measures log queries only, not all four tool families.

## Limits

These are repeated sequential measurements on one developer machine and small
SQLite data, not independent deployment samples. They exclude model latency,
PostgreSQL, contention, disk failures, operator review and real-user traffic.
No performance acceptance threshold was agreed, so these numbers are measurements,
not a production-readiness pass. They establish no detection precision or recall.

The recorder logs completed calls, not durable pre-execution attempts. Worker
crashes or event-write failures can leave missing observations; rejected unknown
tools and malformed calls may not reach the recorder. A real shadow deployment
must measure those paths before claiming complete coverage.

## Reproduce

From the repository root, choose a new output file:

```sh
.venv/bin/python services/ingestion-service/measure_recording.py \
  --rounds 3 --pairs 100 --output /tmp/investigator-recording-new.json
```

The command refuses existing output files and removes only its temporary database.
`source/` preserves the six source files whose hashes appear in the measurements.
Verify the original artifacts from this directory with:

```sh
shasum -a 256 -c SHA256SUMS
```

The explanatory README is outside those checksums. No paid requests, production
changes, commits or publication accompanied these measurements.
