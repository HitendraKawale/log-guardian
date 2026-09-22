# Recurring detection verification

Implemented on `feat/33-recurring-incidents`, based on onboarding commit `4abd403`.
Changes remain uncommitted. This verifies the operational detector, not a product
release, security detector, or application-log accuracy benchmark.

## Executed checks

```text
make test:       370 passed
make test-demo:    6 passed, 2 deprecation warnings
make lint:      All checks passed; 109 files already formatted
PostgreSQL:       1 integration scenario passed
Chromium:        34 passed
git diff --check: no output
```

Commands ran from the suite directories, using the shared root virtualenv:

```sh
make test && make test-demo && make lint
cd tests
LG_TEST_POSTGRES_URL=postgresql://postgres:lg33-test-only@127.0.0.1:18433/lg33 \
  ../.venv/bin/python -m pytest integration/test_incident_detection.py -q
FRONTEND_URL=http://127.0.0.1:18435 INGESTION_URL=http://127.0.0.1:18439 \
  ../.venv/bin/python -m pytest e2e -q
```

The password above belonged only to a disposable localhost test container.
PostgreSQL tests create a fresh database on an explicitly supplied test server.
They verify populated migration 0005 -> 0006, preservation of legacy rows,
concurrent first observations, exact counts, recurrence, lock timeout, preserved
logs, concurrent promotion idempotency, frozen promoted scope and refusal of a
lossy downgrade. SQLite covers the same detector rules and migration behavior,
plus connection-pool timeout restoration and deadline inclusion of pool waits.

CI now installs ingestion dependencies for the PostgreSQL test and supplies its
existing disposable Compose database URL. Hosted CI was not run: this branch has
not been committed or pushed. The full Kafka/Jaeger/Prometheus integration stack
was not started locally; the existing direct/consumer unit tests were included
in the ingestion suite. Browser tests included static-demo and investigation
regressions, not only the new candidate view.

## Real collector, faults, restart and recurrence

Task-owned checkout/inventory containers used the existing onboarding demo images.
The owner-run forwarder followed native Docker stdout for checkout under the
service identity `lg33-checkout`. It delivered to a fresh SQLite API with scoring
and investigation execution disabled. API and frontend bound only to loopback;
these disposable verification servers used no log key. Separate API tests checked
the detector endpoint's log-key boundary.

Two cycles each performed one healthy checkout, six genuine inventory deadline
failures, a fault reset in `finally`, and one recovered checkout. The test waited
for the actual ten-minute quiet interval, not a shortened production threshold.
Each fifth error selected a candidate; the sixth updated its count to two
observations since selection. INFO records did not keep the incident active.

First incident: `6d7aec57-415a-4471-80ec-3a9eb9fd824a`.
Second incident: `6f12bd0f-595e-4213-931e-81e8cf7aeddb`.
The first remained dismissed; the second was new. The first API restart retained
all 16 observations. A final-code restart preserved both incident IDs and review
states. No investigation execution was enabled. Runtime counters recorded zero
detector failures and zero timestamp exclusions in this scenario.

The first harness assertion read a checkpoint before the collector delivered its
last recovery record: it compared 15 observations before restart with 16 after.
The corrected check compared persisted state with all 16 stored records, then
continued the original quiet interval. The failed assertion and logs remain in
the evidence directory; no fault sequence or detector threshold was altered to
hide it.

Browser verification used Agent Browser with named task sessions on:
`http://127.0.0.1:18435/?api=http://127.0.0.1:18434`.
It exercised the Candidates tab and All filter, showing the prior dismissed/quiet
incident beside the new active incident. The full screenshot was captured and
browser error collection was empty. The automated suite separately covered
keyboard dismissal, learning/ready states, count updates, detector-fetch failure,
promoted-link preservation and malicious log rendering.

Portless aliases were registered but its proxy was unavailable. Verification used
the pinned fallback ports above without starting or modifying that shared proxy.

## Local latency check

Three alternating runs of 100 sequential `persist_log` calls compared onboarding
commit `4abd403` with this working tree. Each run used a fresh SQLite database,
timely INFO records, the same Python environment and a no-network AI stub. Schema
creation was outside the timed region. This measures local persistence overhead,
not HTTP throughput or production load.

| Version | Median of run medians | Per-run p95, ms | Detector failures |
| --- | ---: | --- | ---: |
| Original novelty path | 1.401 ms | 1.661, 1.560, 1.633 | 0 |
| Durable detector | 3.601 ms | 5.050, 4.283, 5.182 | 0 |

Measured median overhead was approximately 2.2 ms in this setup. These runs
preceded the final pool-acquisition deadline adjustment; the detector algorithm
and database work were unchanged, but do not treat these as a final-code load
benchmark. The final deadline regression and full suites passed afterward.

## Evidence and cleanup

Local artifacts:
- `/tmp/lg33-final-verified.log`: final offline suites, demo and lint.
- `/tmp/lg33-final-pg-verified.log`: PostgreSQL test output; a later direct rerun
  also passed after the final pool-deadline change.
- `/tmp/lg33-all-browser.log`: full Chromium suite.
- `/tmp/lg33-live/recurrence-result.json`: both incidents and restart observation count.
- `/tmp/lg33-live/scenario.log`, `resume-scenario.log`: original checkpoint race and successful continuation.
- `/tmp/lg33-live/collector.log`, `api*.log`, `live-metrics.txt`: ingestion and detector observations.
- `/tmp/lg33-live/recurring-incidents-full.png`, `final-snapshot.txt`, `browser-errors.txt`: visible UI evidence.
- `/tmp/lg33-live/latency.py`, `latency-results.jsonl`: comparison harness and samples.
- `/tmp/lg33-live/browser-screenshots/`: test-generated images copied outside tracked files.

The disposable PostgreSQL server, sandbox containers, collector, scorer and
browser-suite API are cleaned up after verification. The task API/frontend stay
available on ports 18434/18435 for local review, with provider execution disabled.
Their PIDs and logs live in `/tmp/lg33-live/`; shared onboarding containers remain
untouched. No provider calls, BGL held-out evaluation, commits, pushes or PRs were
performed for this milestone.

## Remaining product limits

Detection is best-effort, not replayed after a failed transaction. Counts include
re-delivered duplicate logs. Minute boundaries can split bursts, and grouping by
service can combine unrelated faults. Thresholds are initial rules, not measured
accuracy. SQLite serializes writers; retention and service-cardinality limits
remain unimplemented. Quiet is not proof of recovery.

Wide events, security rules, durable cumulative investigation budgets and the
paid dashboard workflow remain separate milestones.
