# Initial evidence verification

The server now supplies C's first model request with a bounded unfiltered log
sample from the owner scope. These results use scripted HTTP responses and the
real worker, SQLite storage and SDK. No paid provider request was made.

## Observed

- All ten first HTTP requests contained every observation in their small fixture:
  35 observations total, including all five injected messages.
- A separate read-only SQLite connection verified that the server-initial request
  and completion had committed before each first HTTP request reached the mock
  transport. Both events carry origin=server_initial.
- No out-of-scope inventory canary appeared in those requests. Log messages remained
  in tool content, not system instructions.
- In this preserved rehearsal, scripted replies requested one additional summary
  per case, then returned an inconclusive report. Twenty simulated SDK requests
  completed. Their token/cost fields are test inputs, not real usage or charges.
- The separate fault rehearsal retained an unresolved initial request after a
  completion-write failure and executed no tool after a request-write failure.
  Both failures prevented model execution. Three authored scope denials remain
  distinct from the initial authorized reads.

First-request delivery is the demonstrated change. Model resistance, diagnosis
quality and detector recall were not measured. The earlier live pilot delivered
one of five attacks, but that is not a before/after effectiveness comparison with
this scripted run.

## Limits and checks

The returned sample remains capped at 50 rows and 16 KiB. Truncation, unavailable
sources, the 64-KiB evidence budget, eight-tool budget and 120-second deadline are
covered by tests. Initial reads consume one tool execution; missing-provider runs
perform none. Tests also cover cancellation, storage failure, duplicate initial
queries, the private hook remaining unavailable to the model, and attempts to forge
origin metadata through tool arguments. A/B behavior is unchanged.

530 offline tests and six demo tests passed. The eval suite also passed all 170
tests with pytest-asyncio disabled in an actual shallow local clone that lacked
the historical base commit. This reproduces the cause of the previous hosted CI
failure: a live-only provenance check incorrectly ran in scripted tests. Live
execution still requires its historical base and the other authorization gates.
The hosted branch has not been updated or rechecked remotely.

## Provenance

The working tree was based on 8310cce, with uncommitted changes. That revision is
not the new implementation's identity; `manifest.json` and `candidate/` capture
the executed source hashes and bytes. The pilot wrapper's production_base and
authorization fields describe its historical live gate, not a renewed allowance.
Its execution_mode is scripted, and no live ledger was claimed or reopened.

`coverage.json` records first-request coverage and pre-HTTP committed event sequences.
The request/response witnesses and case exports preserve the actual scripted flow.
`*.db.gz` are lossless copies of the closed SQLite databases. `checks/` preserves
additional regression-test and fault-rehearsal source. `coverage-driver.py.txt` is
the executed standalone driver, retained as text rather than a runtime module.
Run it from the repository root with Python and a new output-directory argument.

`verification.txt`, `shallow-checkout.txt` and `shadow-rehearsal.json` preserve the
checks. Verify with `shasum -a 256 -c SHA256SUMS` from this directory. This README
was added after checksums. Earlier input fixtures, freezes and result archives
were not rewritten. No commit, push, deployment or new paid batch was performed.
