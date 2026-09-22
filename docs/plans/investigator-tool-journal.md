# Pre-execution tool journal

The owner approved the next audit checkpoint. Continue in issue #40; no paid calls,
production deployment, commits or publication.

## Goal

The recorder currently writes only after execution, so a failed write can erase
all evidence of a completed tool call. Commit a redacted request before dispatch,
link the completion to it, and preserve unknown outcomes without inventing success.

```text
[Cancel check] -> [Commit request] -> [Execute tool] -> [Commit linked completion]
                        |                                      |
                failure: do not run                  failure: request unresolved
```

| File | Decision |
| --- | --- |
| `app/investigator.py` | Reuse InvestigationEvent and the existing recorder; return committed sequence, redact arguments without changing actual tool input, add request_sequence to completion |
| `app/investigation_shadow.py` | Pair requests/completions; reject mismatched or duplicate links; retain unresolved requests as unknown; still support historical completion-only events |
| Worker/journal/shadow tests | Verify a request is visible through a separate file-backed DB connection before execution; inject pre/post write failure; verify privacy, linkage and unchanged cancellation |
| `rehearse_shadow.py` | Preserve the old post-execution failure scenario and add pre-execution failure; do not overwrite previous artifacts |
| `measure_recording.py` | Count both journal entries per successful call; repeat paired latency measurements |

All code paths are under `services/ingestion-service/`. Existing event kind is a
string and payload is JSON, so no schema migration is required. Keep tool_call
completion shape compatible apart from the added link. The API already returns
arbitrary event kinds; the UI renders other kinds as plain JSON. No UI redesign.

## Execution checklist

- [x] Add failing journal and pairing regressions, adapting existing completion counts.
- [x] Commit tool_request before calling the tool. If commit fails, propagate failure
  and do not execute. Keep scope enforcement and cancellation behavior unchanged.
- [x] Pair only earlier requests with matching tool/arguments. An unpaired request
  means outcome unknown, including cancellation or process death during execution.
  A completion without a link is historical, not proof of a request record.
- [x] Run the worker rehearsal with selective pre/post event-write failures.
- [x] Run two new paired SQLite measurements and preserve source snapshots/checksums.
- [x] Run all offline suites, demo tests, lint and relevant consumer checks.

No automatic replay: a persisted request does not authorize re-executing a tool.
Unknown/malformed calls rejected in the adaptive loop before dispatch remain
run-level status events, not journaled requests. Durability here means acknowledged
DB commit, not a verified physical power-loss guarantee. Total database outages,
concurrency and real-user alert workloads remain separate validation work.

## Results

461 offline tests and six demo tests passed. A separate-engine read verified the
request commit before execution; an injected failure after insert but before commit
rolled back without executing the tool. The ten-case rehearsal preserves one
unresolved request after completion-write failure and prevents execution after
request-write failure.

Self-review also found that redaction can change argument validity. Altered inputs
now carry arguments_redacted and receive an indeterminate baseline comparison.
Original arguments still reach the actual tool unchanged.

Final paired added median latency: 3.064 ms and 3.068 ms for local 50-row queries.
All 1,260 request/completion events across two executions persisted. This is not
production throughput or physical power-loss evidence.

Final evidence: `evals/results/2026-09-22-investigator-journal-reviewed/README.md`.
The initial journal measurements remain separately preserved. No browser check,
paid model call, production deployment, commit or publication was performed.
