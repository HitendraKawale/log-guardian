# Pre-execution journal verification

The worker now commits a redacted tool_request before each registered tool body
and links its tool_call completion using request_sequence. Request-write failure
stops execution. Completion-write failure leaves a request with unknown outcome.
No automatic replay or assumption of success is introduced.

## Controlled failure results

Ten scripted-provider scenarios used the real worker, tools and SQLite database:

| Condition | Observed result |
| --- | --- |
| Six ordinary/denied calls | Six committed request/completion pairs; three scope denials |
| Unknown tool or malformed call | Rejected before dispatch; still represented only by run status |
| Completion-recording outage | Actual query completed; committed request retained; outcome unknown |
| Request-recording outage | No tool execution and no request record; run failed |

Separate file-backed tests used an independent engine to read the committed
request before entering the tool body. Another test inserted the request but
injected failure before commit: the transaction rolled back and the tool did not
execute. These verify commit ordering and rollback, not physical power-loss durability.

The reviewer pairs matching tool/argument records, rejects duplicate or mismatched
links, and supports historical completion-only events without claiming they had
request records. Redaction never changes the actual tool input. Altered arguments
are marked arguments_redacted; their baseline comparison is indeterminate, because
sanitized text may no longer satisfy the original schema or preserve identifiers.

## Cost of the additional write

Same sequential 50-row query experiment as the earlier checkpoint, two independent
executions on the same developer machine, each with three rounds of 100 measured
pairs and five warmup pairs per round:

| Measurement | First | Repeat |
| --- | ---: | ---: |
| Unrecorded median | 1.909 ms | 1.938 ms |
| Journaled median | 4.977 ms | 5.015 ms |
| Paired added median | 3.064 ms | 3.068 ms |
| Paired added p95 | 3.867 ms | 3.784 ms |
| Persisted request/completion events | 630 | 630 |

All returned batches matched their unrecorded counterparts. Across both executions,
600 measured pairs and 1,260 events including warmup were verified. Earlier
completion-only recording measured about 2.1 ms added median. This is a local
comparison, not a production latency or throughput guarantee. The earlier journal
checkpoint also produced higher timings; those remain preserved in
`../2026-09-22-investigator-journal/`. Do not attribute timing differences to the
redaction metadata change: these runs do not isolate that effect.

## Verification and limits

461 offline tests and six demo tests passed; lint and whitespace checks passed.
The ingestion suite includes API consumer tests. No frontend code changed and no
browser UI verification was performed in this checkpoint; requests use the
existing generic JSON event renderer. Logs: `/tmp/lg40-journal-red.log`,
`/tmp/lg40-journal-redaction-red.log`, `/tmp/lg40-journal-final-tests.log`.

This remains synthetic engineering evidence with self-review. No independent
attack evaluation, paid model calls, production deployment or real-user traffic.
The journal does not capture unknown/malformed requests rejected before dispatch.
A committed request proves intent was recorded, not that execution began or
succeeded. Cancellation can race with execution; there is no atomic transaction
spanning cancellation, the journal and a remote tool. Full database outages,
process/power-loss drills and contention remain untested.

`SHA256SUMS` covers the three result files and nine source snapshots. This README
was added afterwards. Verify with `shasum -a 256 -c SHA256SUMS` from this directory.
Reproduce from the repository root with new output paths:

```sh
.venv/bin/python services/ingestion-service/rehearse_shadow.py --output /tmp/journal-rehearsal-new.json
.venv/bin/python services/ingestion-service/measure_recording.py --output /tmp/journal-timing-new.json
```

No prior artifacts were overwritten. Nothing was committed or published.
