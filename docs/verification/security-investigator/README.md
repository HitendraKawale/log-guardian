# Security investigator connection verification

Issue #48, based on e0a7926 plus this milestone's changes. The user explicitly waived
the unavailable Plannotator gate with "just do it". No paid request, live provider
worker, customer-data import, merge or deployment was performed.

## Executed checks

```bash
make test && make test-demo && make lint
```

`local-verification.txt` records the full output. Relevant lines:

```text
36 passed in 1.19s
356 passed in 23.35s
12 passed in 0.02s
6 passed in 0.06s
286 passed in 19.58s
40 passed in 6.05s
22 passed in 0.48s
6 passed, 2 warnings in 3.58s
All checks passed!
398 files already formatted
VERIFY_EXIT=0
```

That is 758 offline checks and six demo checks. Existing pytest-asyncio configuration
warnings and two demo websocket deprecation warnings remain. The 33 new service
checks also passed together after the final review changes.

The full Chromium suite ran from tests/ against task-owned services:

```bash
INGESTION_URL=http://127.0.0.1:8480 \
AI_URL=http://127.0.0.1:8482 \
FRONTEND_URL=http://127.0.0.1:8480/ui \
../.venv/bin/python -m pytest e2e -q --tb=short \
  --basetemp=/tmp/lg48-connection-browser-verified
```

```text
40 passed in 39.18s
```

`browser-verification.txt` records the result. Security-page tests use isolated real
API processes with file-backed SQLite. The provider runs through httpx.MockTransport
inside the test harness only, with no real transport fallback or product fake-mode flag.
An idle-worker variant verifies queued cancellation and reopening without a second run.

The browser flow verifies import creates no investigation, a review key cannot spend,
an explicit execution-key action queues one run, a lost promotion response can be
retried without duplication, and a completed report opens its recorded citations.
Reload requires re-entering keys. Endpoint changes clear the execution key and draft.
Both browser storage objects remain empty; credentials never enter the page URL.
Hostile report HTML remains text. Desktop and 390px layouts have no page overflow.
Expected 401 responses and deliberately aborted responses exercise failure handling;
they are not unexplained network failures.

`desktop.png` and `mobile.png` show that actual scripted-worker flow. The six authored
example records produce three links, two failures and one success. The visible
observation starts with "Scripted check". These are not screenshots of a real model's
security assessment.

## Storage and concurrency

The integration command ran with LG_TEST_POSTGRES_URL pointing at the task-owned
PostgreSQL 16.15 container's current loopback mapping, obtained using docker port,
and LG_TEST_NGINX_IMAGE=nginx:alpine:

```bash
cd tests
../.venv/bin/python -m pytest \
  integration/test_security_import.py integration/test_security_nginx.py -q -s --tb=short
```

```text
PostgreSQL imports, migration and one-winner promotion verified in fresh database lg_security_b43e49f1b5ef4860a87ba59f0e80b0c7
nginx -t passed; generated ID reached upstream; query and client ID absent from log
2 passed in 2.06s
```

`integration-verification.txt` preserves the output. PostgreSQL upgraded from 0007 with
an existing investigation and journal event, preserved both, and admitted exactly one
new run under four concurrent promotion attempts. SQLite has its own file-backed
four-way promotion check and upgrade/refused-downgrade checks. No pre-existing database
was dropped. The task-owned PostgreSQL container was stopped after verification.

The nginx check remains a real local request to a synthetic upstream, not an identity
provider or customer application. The older full Kafka/Jaeger integration suite was
not rerun locally.

## Worker protocol evidence

`scripted-run.json` comes from the executed worker test, not hand-authored receipts.
This smaller fixture contains one gateway HTTP 200 and one explicit authentication
failure. A second case is seeded with an OTHER_CASE_CANARY account reference; the test
asserts that marker never reaches the first case's provider request.

The artifact records:

- One scripted provider request and zero real model requests.
- Only read_security_evidence in the advertised tool list.
- The saved source snapshot, actual first-request body and accepted synthetic report.
- Committed tool_request and linked tool_call before the provider handler is entered.
- A completed status event, prompt hash, source binding and internal S discriminator.

Usage values are synthetic, and estimated_cost_usd is an estimate computed from those
invented token counts, not money spent. code_revision is the parent commit because
verification ran against the working tree before committing. This is not a live
execution freeze or an independent semantic evaluation.

Other checks cover contiguous byte-limited pages over 200 long-identifier records,
stable citations, empty/missing/ambiguous evidence, forbidden source/scope arguments,
unknown citations, tool/cost/evidence/deadline exits, missing provider, outage,
cancellation, and failed intent/completion writes. A separate SQLite connection
observes committed security-tool intent before the tool body executes.

## Failures found and resolved

- Initial promotion checks returned 404; the migration check found no binding column;
  tool/worker checks lacked the security source; the browser check found no execution
  input. These checks went green after implementation.
- The full suite exposed inconsistent POST/GET case representations after adding the
  linked run ID. Both now use the same serializer. The old 0007 migration test now
  targets 0007 explicitly; the new upgrade test covers head and existing journal data.
- A privacy regression showed investigation reads lacked Cache-Control: no-store.
  The shared authorization dependency now sets it for successful responses.
- Two PostgreSQL attempts used an obsolete loopback port after restarting the container.
  Docker had reassigned its dynamic host port. The verified run used the actual mapping.
- Self-review found old workers would interpret a new security case stored as C as an
  ordinary operational investigation. A test executed the unchanged archived dispatch
  implementation and caught an attempted scripted provider request on the wrong source.
  New security runs store S. Old dispatch rejects S before any provider call; the current
  worker validates the case binding and then executes C. The public API still reports C.
  Stop old workers before enabling case execution, since they may fail such runs.

## Local inspection and limits

The task-owned API was migrated and restarted with current code. It remains at:

`http://127.0.0.1:8480/ui/security.html?api=http://127.0.0.1:8480`

The existing pinned loopback server was reused; no shared portless proxy settings were
changed. Local review and execution keys remain in the mode-0600 file
/tmp/lg48-review-runtime.json, outside the repository. No provider worker is running
there, so new local runs remain queued until an authorized worker executes them.
The completed scripted reports in the screenshots belong to isolated test databases.

One case still gets one run, with no paid retry feature. Large cases can exhaust the
unchanged budgets before every record reaches a provider. Counts remain scoped and
collection completeness unknown. A namespace is an owner assertion, not a verified
network topology. Citation membership is not semantic support. No live accuracy,
independent labels, production capacity, automated remediation or AI attribution claim
follows from these checks.

The diff received self-review, not independent review. No subagent review tool was
available. Frozen research archives, manifests and spending ledgers were not edited.
The business-security README/preview rewrite and external interview correction remain
separate work.
