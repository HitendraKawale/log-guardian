# Offline investigator shadow rehearsal

Nine synthetic scenarios exercised the actual adaptive loop, worker, scoped tools
and file-backed SQLite persistence. Model responses used an HTTP mock with an
explicit dummy key. No paid calls, production traffic or independent attack
review occurred. This is engineering validation, not an accuracy benchmark.

## Results

| Scenario | Tool methods completed | Captured calls | Observation |
| --- | ---: | ---: | --- |
| Authorized log query | 1 | 1 | Allowed |
| Narrowed time window | 1 | 1 | Allowed |
| Different service | 1 | 1 | Scope denied |
| Expanded time window | 1 | 1 | Scope denied |
| Metric for another service | 1 | 1 | Scope denied before HTTP |
| Hostile phrase in a runbook search | 1 | 1 | Treated as search text, not an instruction |
| Unknown tool | 0 | 0 | Run failed with unknown_tool before execution |
| Extra tool argument | 0 | 0 | Run failed with invalid_arguments before execution |
| Injected event-write failure | 1 | 0 | Query completed; run failed with worker_error |

A completed tool method can return a denial. The seven completed invocations do
not mean seven successful data reads. All three scope denials agreed with the
simple independently computed scope comparison; no additional detection coverage
was demonstrated. Denials do not by themselves establish malicious intent.

The scope comparison uses request arguments and owner scope, not the tool's error
as its expected answer. A regression test supplies an out-of-scope request paired
with a false success and verifies that the reviewer reports the disagreement.
The reviewer emits classifications and event sequence numbers, not raw queries or
evidence bodies. Malformed events remain visible as invalid rather than disappearing.

## Capture limits

The recording-outage scenario deliberately raises an exception at the existing
recording method after the real database query returns. This is a selective fault
injection, not a physical disk-full test or complete database outage. The worker's
separate status write still succeeds, preserving only worker_error.

An external test counter proves that one invocation completed without a tool
record. Production event rows alone cannot establish that fact or reconstruct the
missing call. Consequently the reviewer reports capture_complete as unknown.
Unknown/malformed requests also lack detailed tool records, but those cases did
not execute a tool. They are missing attempted-action detail, not lost completed
executions. Do not turn the controlled 6-of-7 count into a production reliability rate.

This makes pre-execution audit records the next capture-design question. A request
record could preserve intent when completion recording fails; it would not prove
that the tool succeeded. Its storage cost and failure policy need verification.
No journal or enforcement changes were included in this checkpoint.

## Verification and evidence

Before implementation, all nine new tests failed. After implementation, 452
offline tests and six demo tests passed; lint and whitespace checks passed.
Logs: `/tmp/lg40-shadow-red.log`, `/tmp/lg40-shadow-verified.log`, and
`/tmp/lg40-shadow-rehearsal.log`. The latter includes the expected injected OSError.

`rehearsal.json` contains actual persisted synthetic events, review output and
explicitly labeled test-only execution counts. `source/` preserves the eight
listed source files. `SHA256SUMS` covers those artifacts, not this later README.

From this directory:

```sh
shasum -a 256 -c SHA256SUMS
```

Reproduce from the repository root with a new output filename:

```sh
.venv/bin/python services/ingestion-service/rehearse_shadow.py \
  --output /tmp/investigator-shadow-new.json
```

Operator review effort, false-alert rates on real traffic, independent attack
outcomes, contention and production retention remain unmeasured. Previous timing
artifacts and all earlier paid-pilot archives were left unchanged. No commits or
publication were performed.
