# Deterministic security assessment verification

The factual assessment reads a saved case without provider access or an Investigation row.
Optional AI errors remain errors and do not replace the baseline. This change does not establish
production capacity, source authenticity or detection accuracy.

## Checks executed during implementation

- The original offline suite passed before changes.
- The initial builder test failed because build_security_baseline was absent. It passed after
  implementation alongside the unchanged model-selection tests.
- All four committed synthetic business fixtures generated assessments without model selections.
  Their saved-record counts are 19/8/6/8. Case 3 leaves authentication unknown; case 4 does not
  qualify for the repeated-failure hypothesis.
- Boundary checks cover 1,000 records, multiple pages, duplicate/conflicting evidence, invalid
  offsets, redacted identities, equal timestamps, empty inputs and byte-limited display prefixes.
- The new endpoint initially returned 404. Its passing tests disable the execution key, prohibit
  outbound HTTP, assert zero Investigation/event rows and compare repeat response bytes.
- Separate checks prove a changed/missing current registry and existing failed/cancelled AI runs
  do not change baseline bytes or mutate stored evidence, reports or events.
- The full ingestion, contract and eval suites passed before UI work.
- Chromium exercised baseline display before AI consent, scripted provider/selection failures,
  keyboard citations, mobile width, hostile text, unknown versions, connection/case changes,
  memory-only credentials and the review-key-gated deep link outside the first history page.
- The compatibility browser run printed `33 passed in 55.89s` and `BROWSER_EXIT=0`.

Two failures in the original browser assertions were expected after adding the independent panel:
they treated "Recorded facts" as page-wide instead of referring to the AI panel. Their corrected
assertions still preserve legacy model-written claims while the baseline remains visible.
A new stale-connection test initially waited for an HTTP response after the UI aborted its request.
It now observes request failure and verifies that no stale assessment appears. No application
change was needed for that test correction.

## Final verification

Executed from the isolated worktree with OPENAI_API_KEY, OTEL_CONSOLE and
OTEL_EXPORTER_OTLP_ENDPOINT empty:

```bash
make test
make test-demo
make lint
cd tests
../.venv/bin/python -m pytest e2e/test_security_review_ui.py e2e/test_static_demo.py e2e/test_investigations_ui.py -q --basetemp=/tmp/lg48-deterministic-final
```

The captured output in verification.txt includes:

```text
36 passed in 1.47s
433 passed in 24.59s
12 passed in 0.02s
6 passed in 0.06s
291 passed in 21.56s
40 passed in 6.71s
22 passed in 0.49s
6 passed, 2 warnings in 3.67s
All checks passed!
517 files already formatted
33 passed in 54.91s
VERIFY_EXIT=0
```

That is 840 offline tests, six demo tests and 33 browser tests. Existing pytest-asyncio
loop-scope and websockets deprecation warnings remain. The four preserved live archives
passed their standalone verifiers and SHA256SUMS checks; archive-checks.txt records the output.
The latest untracked archive was checked in the original 48-typed-security worktree and
was neither copied into this branch nor modified.

source-sha256.json records tested source/document bytes. SHA256SUMS covers the verification
artifacts. Raw red-test output retains its original whitespace. Existing generated operational
and static-demo screenshots were backed up under /tmp/lg48-deterministic-generated-screenshots
and restored to their original tracked bytes, rather than included as unrelated changes.

No paid model calls, commits, pushes or deployment occurred for this change. Browser providers
use MockTransport only, with invented usage. The implementing assistant performed the initial
review; no reviewer subagent was available. The owner subsequently reported code review completed
with no changes requested. Historical paid outcomes remain unchanged.

## Read-only viewer

http://127.0.0.1:8488/ serves separate copies of the latest closed batch's four databases,
using this worktree's API and frontend. Command: the shared venv's Python running
/tmp/lg48-deterministic-viewer.py. Portless is installed but its shared HTTPS proxy is stopped;
this viewer uses the pinned loopback fallback without changing proxy setup.

Chromium can follow the smoke-*.localhost links. Plain loopback selects smoke-03. Review and
execution keys are in owner-only /tmp/lg48-deterministic-viewer-runtime.json, not in this archive.
No provider credential or worker exists in the viewer. Every write method returns 405.
Other worktrees, earlier viewers and original ledger databases were left untouched.

The viewer check printed:

```text
smoke-01: baseline reviewed 19/19; historical AI completed; citations opened; POST 405; storage empty; desktop/mobile no overflow or page errors
smoke-02: baseline reviewed 8/8; historical AI failed; citations opened; POST 405; storage empty; desktop/mobile no overflow or page errors
smoke-03: baseline reviewed 6/6; historical AI completed; citations opened; POST 405; storage empty; desktop/mobile no overflow or page errors
smoke-04: baseline reviewed 8/8; historical AI failed; citations opened; POST 405; storage empty; desktop/mobile no overflow or page errors
PASS: 41 saved records reviewed without model execution; historical reports unchanged.
```

The screenshots include all four copied cases on desktop/mobile plus no-worker and scripted
AI-failure examples. The viewer check opened citations, left the execution key input empty,
verified the missing-auth unknown and checked the original failed runs still have null reports.
It closed its Chromium sessions. The read-only viewer remains running for owner inspection.
The timeout during an early browser-test run left no process holding its task-owned server logs.

## Review status

The owner reported implementation code review completed with no changes requested. All 16 plan
steps are complete. The review patch included source, tests, documentation, the approved plan and
this verification summary; raw logs and screenshots remained in the evidence directory.
No independent quality evaluation, load test, live AI-ranking comparison or production rollout
was performed. Review completion does not authorize a commit, push, deployment or paid batch.
