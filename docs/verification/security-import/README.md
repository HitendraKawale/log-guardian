# Nginx/authentication import and review verification

Issue #48. Based on 5909e1b plus this milestone's changes. The owner selected nginx
and structured application authentication logs and authorized implementation, commit
and push. No paid model request, customer log import, account attack or deployment.

## What ran

```bash
make test && make test-demo && make lint
```

`local-verification.txt` preserves the full output. Relevant lines:

```text
36 passed in 1.27s
323 passed in 21.44s
12 passed in 0.01s
6 passed in 0.06s
286 passed in 17.46s
40 passed in 6.03s
22 passed in 0.47s
6 passed, 2 warnings in 3.58s
All checks passed!
392 files already formatted
VERIFICATION_EXIT=0
```

That is 725 offline tests plus six demo tests. Existing pytest-asyncio configuration
warnings and two demo websocket deprecation warnings remain.

The full Chromium suite ran against task-owned API and scorer services, not the
existing shared local stack:

```bash
cd tests
INGESTION_URL=http://127.0.0.1:8480 \
AI_URL=http://127.0.0.1:8482 \
FRONTEND_URL=http://127.0.0.1:8480/ui \
../.venv/bin/python -m pytest e2e -q --tb=short
```

```text
38 passed in 33.98s
```

`browser-verification.txt` records the result. The new page's checks use isolated real
API processes and SQLite files. They cover upload, replay, reload, history, citation
opening, rejected input, wrong keys, 390px layout, no persistent credential storage,
text-only rendering and a deliberately lost response after a successful server commit.
The retry check confirms the same import key returns the original case.

The PostgreSQL/nginx checks ran with LG_TEST_POSTGRES_URL pointing at a task-owned
PostgreSQL 16 container and LG_TEST_NGINX_IMAGE=nginx:alpine:

```bash
cd tests
../.venv/bin/python -m pytest \
  integration/test_security_import.py integration/test_security_nginx.py -q -s
```

```text
PostgreSQL security evidence verified in fresh database lg_security_4221035ca2b042bf83797d5fd8da832c
nginx -t passed; generated ID reached upstream; query and client ID absent from log
2 passed in 1.63s
```

`integration-verification.txt` preserves output. The PostgreSQL check creates a fresh
database, upgrades migrations, races identical and overlapping imports, rejects
conflicting evidence, reads paginated summaries and verifies zero paid Investigation
rows. SQLite's upgrade check preserves a pre-existing operational log.

The nginx check sends a real local request containing an attacker-selected request ID,
a forged forwarding header and a query token to the configured gateway. A synthetic
upstream reports the ID it received. It is a generated 32-character hex value, matches
the access-log record, and is not the client's ID. The log contains neither the query
token nor the forged forwarding address. This upstream is not a real identity provider.

## Manual browser evidence

Agent Browser session lg48-security-review exercised:

`http://127.0.0.1:8480/ui/security.html?api=http://127.0.0.1:8480`

The task-local server mounted the existing frontend under /ui beside the real API.
Portless was installed, but its shared proxy was stopped; no proxy or trust settings
were changed. The task server used the free loopback port 8480 and a temporary SQLite
database. The scorer used 8482 for the unrelated operational dashboard regression tests.

- Connected with an owner key, selected the two authored files, saved a review and
  opened the edge/r1 citation.
- Observed three linked requests, two recorded authentication failures and one success.
- Checked localStorage and sessionStorage: both empty.
- Checked desktop and 390px document width: no page overflow.
- Agent Browser reported no page errors or console messages in that flow.

`desktop.png` and `mobile.png` show the real UI and imported synthetic records.
`saved-review.json` is the actual API response, including its input hashes and owner
source snapshot. No credential is present in these artifacts. The browser session was
closed; the local review app remains available for inspection while the task server runs.

## Failures found and resolved

- Adapter/API tests failed before the modules, tables and routes existed. A later test
  exposed acceptance of an extra unconfigured service in scope; exact source-service
  matching now rejects it.
- The first full suite hit three historical fresh-pilot checks because they compared
  the changed product config/main/models with frozen research hashes. Their original
  check code now runs in a child process importing an extracted, SHA-256-verified copy
  of the original application. The original checks are preserved byte-for-byte in
  `_fresh_pilot_checks.py`. Archives, manifests and the live runner were not changed.
  An additional test confirms the evolved product cannot reuse the old live candidate.
- The first nginx readiness probe saw a connection close before startup completed.
  The bounded wait now handles that condition while still checking container failure.
- The first full browser run used default URLs for an existing protected local stack:
  1 failure, 29 passes and 8 setup errors. No key was supplied to that stack. The verified
  rerun used the task-owned URLs above.
- The new navigation link initially lost the API override. A browser regression caught
  it, and the link now preserves the query string.
- A static-export regression caught the live uploader entering the read-only demo.
  The exporter now excludes the security page/assets and removes its navigation link.

## Limits and work left

The formats are prescribed, not universal log parsers. Collection remains explicit,
not continuous. Source identity and namespace trust are owner assertions; the importer
cannot verify the network topology. Addresses/account references can be sensitive.
The database has no automated retention policy or production-capacity measurement.

The security records are not yet exposed to the paid investigator's evidence tools.
No model narrative, automated attack classification, independent semantic validation,
remediation or AI attribution was added. The external interview document and older
agent-monitor preview still need their planned direction corrections.

Self-review checked authorization-before-body-read, source ownership, atomic conflicts,
idempotency, safe rendering and unchanged research artifacts. No independent/subagent
review tools were available. The old general Kafka/Jaeger integration suite was not
rerun locally; this milestone ran the two new integration checks and all browser tests.
