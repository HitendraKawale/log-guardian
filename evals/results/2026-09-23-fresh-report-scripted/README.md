# Fresh-case scripted preflight

Twelve synthetic cases passed through the real SDK, worker and SQLite journal with
mock HTTP responses. All twelve reports were scripted inconclusive reports, not
model diagnoses. No paid request was made.

`test_fresh_batch_real_worker_and_input_separation` ran directly with its guarded
file access and first-request evidence assertions. All 106 fixture rows reached
the twelve first requests; the outside-scope canary did not. Each initial read had
one server-origin request and linked completion. Reopening the same ledger failed.
Labels, rubric, pair objectives, provenance, build script and corrected-report
examples were unreadable during the run. The runtime source snapshot excludes them.

552 offline tests plus six demo tests passed, with lint clean. Separate checks
exercised 72 reservations with six per case, production/case drift refusal, and
restoration of the consumed batch defaults after the fresh configuration exits.
The original runner's full transport and spending-boundary tests also passed.

Execution digest: c58186843f75aa17abd1c03f177ebdc58ee3bb2718bb848e55bdae374f7cf763.
The rehearsal ran on baseline 1edd36a with uncommitted wrapper changes. Source
snapshots and hashes, not that revision alone, identify the executed wrapper.
The production candidate and fresh corpus remained byte-identical to their freezes.

Token counts and costs in these artifacts are synthetic test values. The recorded
reservation is conservative accounting for the mock requests, not paid usage.
Verify with `shasum -a 256 -c SHA256SUMS`. This later README is excluded from that list.
