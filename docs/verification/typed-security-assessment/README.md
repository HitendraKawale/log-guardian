# Typed security assessment verification

Implemented on feat/48-typed-security from 3fa9e29, without committing or pushing.
The new security contract accepts evidence selections and fixed hypothesis/check codes,
not model-written factual claims. The host renders the selected facts and mandatory
unknowns. This constrains the report; it does not establish security-diagnosis accuracy.

## Executed checks

The shared venv ran these commands with OPENAI_API_KEY, OTEL_CONSOLE and
OTEL_EXPORTER_OTLP_ENDPOINT empty:

```bash
make test
make test-demo
make lint
cd tests
../.venv/bin/python -m pytest e2e/test_security_review_ui.py e2e/test_static_demo.py e2e/test_investigations_ui.py --basetemp=/tmp/lg48-typed-approved-final -q
```

Relevant output from lg48-typed-approved-verification.txt:

```text
36 passed
397 passed
12 passed
6 passed
291 passed
40 passed
22 passed
6 passed, 2 warnings
All checks passed!
516 files already formatted
25 passed in 40.98s
VERIFY_EXIT=0
```

The first seven suites total 804 offline tests. The next six are demo tests. The browser
count covers nine security tests, six static-demo tests and ten operational UI tests.
Existing pytest-asyncio loop-scope and websockets deprecation warnings remain.

All three prior live archives passed their standalone verifiers and existing SHA256SUMS.
The checksum logs are included here. No captured response, historical verdict, source
snapshot, frozen runner, execution allowance or recorded number was rewritten.

## Regressions and browser evidence

The contract test reads the actual archived missing-auth report. Its free-form output
cannot enter SecuritySelection. Selecting its gateway HTTP 200 instead yields a gateway
fact with the original citation and an explicit unknown authentication outcome.

Tests cover conflicting HTTP/auth outcomes, counts without identities, missing/redacted
identities, recorded ordering, ambiguous correlations, code prerequisites, wrong-case or
page IDs, duplicate selections, failed/truncated evidence and conflicting duplicate pages.
Both directions of the v1/v2 workflow-binding mismatch stop before provider calls.

The planned security UI checks passed, then a consumer review found a missed renderer:
frontend/investigations.js also reads security runs from shared history. The browser
reproduced "Cannot read properties of undefined (reading 'length')". The user approved
extending the plan to that file. Its version-aware sections now pass the same regression,
including citation opening and rejection of unsupported report versions. Operational
report behavior passed the ten existing browser tests.

Screenshots:

- typed-missing-auth-desktop.png and typed-missing-auth-mobile.png show the recorded HTTP
  response and mandatory unknown auth outcome, with the source citation opened by keyboard.
- legacy-false-claim-desktop.png and legacy-false-claim-mobile.png show the unchanged
  historical false claim under the legacy-model-draft warning. The browser test substitutes
  the archived report into a GET response solely to exercise legacy rendering; it does
  not claim a new provider produced that report or alter stored history.
- shared-history-v2.png shows the new report in the operational dashboard's shared history.

Chromium exercised the missing-auth flow at
http://127.0.0.1:62647/ui/security.html?api=http://127.0.0.1:62647.
The suite owns its ephemeral-port servers and shuts them down after each test. This URL
is evidence of the test, not a retained review server. Existing viewers were not changed.
Browser checks covered consent and separate credentials, import/promotion idempotency,
keyboard citations, mobile overflow, text-only hostile content, unknown versions and
stale responses after credentials change. The checked flows had no browser script errors.

Only the provider transport was scripted in the security browser tests. Routes, saved
SQLite cases, worker execution, receipts and rendering were real. Displayed token usage
and cost are invented fixture values. No paid model request occurred. Test-generated
screenshots in the pre-existing screenshot directory were copied to /tmp and restored
to baseline rather than included as unrelated changes.

## Review and limits

The implementing assistant reviewed the diff against the approved plan and repo rules.
No independent reviewer or subagent was available. The review caught and reproduced the
shared-renderer compatibility gap rather than reporting the initial green suites as done.

No new dependencies, database migrations, operational report-schema changes, execution-
budget changes, retries or broader evidence tools were introduced. Facts still describe
owner-supplied records, not verified real-world events. The bounded hypothesis vocabulary
cannot confirm compromise or attack intent. Model selection quality has not been tested
with a live provider; another live run requires a fresh authorization.

source-sha256.json identifies the implementation and test bytes checked. Red and green
logs are preserved alongside this report. SHA256SUMS covers the verification files.
