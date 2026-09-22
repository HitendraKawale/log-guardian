# Local project onboarding implementation plan

Status: implemented and verified locally; uncommitted and awaiting code review. Milestone 1 of the approved [product scope](product-release-scope.md).

## Execution checkpoint

Issue: https://github.com/HitendraKawale/log-guardian/issues/31
Worktree: `/Users/hitesh/log-guardian-worktrees/31-local-onboarding`
Branch: `feat/31-local-onboarding`. No commits or pushes.

Implemented the native Docker forwarder and 40 checks, disabled-scorer guards, local Compose profile, latest-log UI and five Chromium checks, Makefile/CI integration, onboarding docs, stdout emission, and source-only Compose profile. These remain uncommitted.

Fresh checks: `make test` passed 345 tests; `make test-demo` passed 5; `make lint` passed with 99 files formatted. The full browser suite passed 31 tests against a separate task-owned stack with the existing classifier enabled, plus its offline stubs. That temporary browser stack has been stopped. Hosted CI and independent code review have not run.

Real local-profile verification passed two fault/recovery cycles, stored 83 application records without fault-control diagnostics, and stopped both collectors with exit 1 during an API outage. A separate native Docker check forwarded a plain-text ERROR record and verified SIGINT exit 130 with its owned child reaped. All verification collectors have stopped. Agent Browser exercised API-key entry, the Logs tab, and filter-independent source observation against the authenticated local profile. No JavaScript page errors were reported; unauthenticated 401s and disabled model/investigation 503s were expected. A fresh browser confirmed the event timestamp matched SQLite's UTC value after a new regression test caught local-time interpretation.

Evidence: `/tmp/lg31-final-verification.log`, `/tmp/lg31-all-browser.log`, `/tmp/lg31-live-evidence-output.log`, `/tmp/lg31-live-evidence/` and `/tmp/lg31-browser-evidence/`. Final local-profile screenshot: `/tmp/lg31-live-evidence/dashboard.png`. The live verification script is `/tmp/lg31-live-verification.py`. These local artifacts are not customer-validation or paid-evaluation evidence.

The local stack at `http://localhost:8080/?api=http://localhost:8000` uses project `lg31-local`; source stack uses `log-guardian-source`. Both were started for this task. The local verification key is `local-test-only`, not a production credential. Scoring is disabled, unauthenticated log reads returned 401, investigations returned 503, and a stored log survived an API-container restart. Portless was not used because its shared proxy is stopped. No paid model calls or archived evidence changes.

### Resolved blocker from real Docker verification

On Docker 29.2.1, `docker compose logs --timestamps --no-color --no-log-prefix inventory` sends both application stdout and owner-only fault stderr to its stdout. The collector's original fake-Docker tests assumed separate streams and did not prove actual Compose behavior. Execution stopped as required before changing the collection mechanism.

A read-only comparison on the same container verified that `docker logs --timestamps <container-id>` preserves the streams:

```text
Compose stdout contains app log: True
Compose stdout contains fault diagnostic: True
Compose stderr contains fault diagnostic: False
Native docker logs stdout contains app log: True
Native docker logs stdout contains fault diagnostic: False
Native docker logs stderr contains fault diagnostic: True
```

The owner approved the correction in chat: resolve exactly one running container with `docker compose ... ps -q <service>`, reject zero/multiple containers and TTY mode, then follow `docker logs --follow --timestamps --tail 0 <id>` with separate stderr. It is implemented and verified on Docker 29.2.1. A stopped source produces a nonzero exit; there is no automatic reconnection or container switching. New tests cover resolution failures, TTY rejection, and stopped containers.

## Context

Log Guardian accepts individual HTTP log records, but does not collect another Compose project's output.
Deliver a localhost installation and an owner-run forwarder without requiring application instrumentation or a Docker socket mount.
Prove forwarding through the existing ingestion API, then verify connection and latest-log visibility in the browser.

## Approach

```text
[Selected Compose service] -> [Owner-run Python forwarder] -> [Existing POST /logs]
                                                                  |
                                                           [SQLite + dashboard]
```

Use Python 3.11 stdlib for the forwarder. No new runtime dependencies, Kafka, classifier container, or model worker. Existing demo and full-stack profiles remain unchanged.

The owner selected checkout/inventory for initial verification. At baseline, `demo/app.py::emit` sent incident records directly to the ingestion API and emitted no stdout record. Add one JSON stdout line per call, before the optional direct HTTP path. Preserve existing direct ingestion for the original demo profile. In a separate source-only Compose file, leave `INGESTION_URL` empty so every stored incident record must travel through the new forwarder. Run one forwarder per service, using `--source-name checkout` and `--source-name inventory` to preserve the scenario's existing service names. Do not forward owner-only fault-control diagnostics as application evidence.

The forwarder resolves one running, non-TTY container through Compose, then owns a native `docker logs` subprocess. Run one selected service per process with `--follow --timestamps --tail 0`. Accept repeated `--file`, a required `--project-name`, required `--service`, and an optional `--source-name` override for the stored service name. Default the stored name to `project/service` so projects do not silently merge. Invoke an argument list, never a shell string. Reject option-shaped project/service values.

Use a bounded line reader with a 64 KiB byte limit. Drain oversized lines and count them as rejected, rather than splitting them into fabricated events. Decode invalid UTF-8 with replacement. Docker's leading timestamp determines event time. Normalize timezone-aware timestamps to UTC; reject missing or malformed Docker timestamps with a counter and no raw log content in diagnostics.

For a JSON object with a nonempty string `message`, use `level` when it matches the existing enum, case-insensitively, accepting WARN as WARNING and FATAL as CRITICAL. Missing level defaults to INFO. Invalid provided levels are rejected visibly. Ignore embedded service and timestamp fields, since the selected source and Docker timestamp own these values. Other text, including malformed JSON and JSON without a usable message, remains a literal message at INFO. A leading bracketed or bare enum severity token may set the plain-text level; do not infer severity from arbitrary words inside messages. Treat multiline output as separate records and document the limitation.

Post synchronously, with a five-second timeout and no automatic retries. Read the next line only after the current request completes. This bounds application buffering and applies pipe backpressure; it does not guarantee Docker retention. On any HTTP or transport failure, stop, report the acknowledged count and uncertain current record, and exit nonzero. Replaying manually may duplicate accepted records. There is no durable spool, exactly-once guarantee, or automatic reconnection in this milestone.

Print status to stderr at startup, on each acknowledged record, on rejection, and on shutdown. Include the selected source, acknowledged/rejected counts, and last acknowledgement time, never credentials or message contents. Read the log API key only from `LOG_GUARDIAN_API_KEY`. Default to a loopback API URL; reject URL credentials and redirects to prevent key leakage. SIGINT/SIGTERM must stop and reap only the child started by this command, with bounded terminate/kill cleanup.

## Reuse

- `services/ingestion-service/app/routes/logs.py`: `POST /logs`, key gating, and newest-first listing already exist.
- `services/ingestion-service/app/service.py`: `persist_log` preserves logs before best-effort detection. Do not replace it.
- `services/ingestion-service/app/schemas.py`: preserve the four-field `LogCreate` contract and existing enums.
- `services/ingestion-service/app/ai_client.py`: both scorer methods can return `None`; use that contract to disable the irrelevant classifier cleanly.
- `frontend/app.js`: reuse `authHeaders`, `setStatus`, polling, and existing filters. API reachability is not collector health.
- `infrastructure/docker/demo-compose.yml`: reuse the SQLite volume and loopback binding pattern, not the demo services or fixed container names.

## Files to modify

| Path | Today | After |
| --- | --- | --- |
| `demo/app.py`, `demo/test_scenario.py` | Incident logs go directly to the API | Emit JSON stdout records even with direct ingestion disabled; test both paths |
| `infrastructure/docker/onboarding-source-compose.yml`, new | Demo profile includes ingestion | Checkout/inventory only, direct ingestion disabled, loopback fault controls |
| `scripts/forward_compose_logs.py`, new | No external project collector | Bounded owner-run Docker subprocess and HTTP forwarding CLI |
| `tests/forwarder/test_forward_compose_logs.py`, new | No collector contract checks | Stdlib fake HTTP and subprocess tests, no Docker daemon required |
| `infrastructure/docker/local-compose.yml`, new | Demo/full-stack profiles only | Two-service local profile with SQLite persistence, required log key, no paid worker |
| `services/ingestion-service/app/ai_client.py` | Always attempts scorer HTTP | Empty base URL returns `None` without network calls in both methods |
| `services/ingestion-service/tests/test_ai_client.py`, new | No explicit disabled-client contract | Assert empty URL makes zero HTTP calls; preserve best-effort failures |
| `frontend/index.html`, `frontend/app.js` | API status and filtered log list | Separate API status and latest stored log observation; never imply a collector heartbeat |
| `tests/e2e/test_dashboard.py`, new `tests/e2e/test_local_onboarding_ui.py` | Existing dashboard checks | Updated connection label; empty, received, unauthorized, offline, filter-independent and UTC latest-log checks |
| `demo/requirements-dev.txt`, new | Demo suite lacked CI setup | Pin pytest for the newly included CI demo job |
| `Makefile`, `.github/workflows/ci.yml` | Existing targets and suite matrix | Local profile targets, forwarder suite, lint new code explicitly |
| `docs/local-development.md`, new; `README.md` | Demo setup | Key setup, selected-project forwarding, parser/delivery limits, troubleshooting |

Read existing tests and referenced browser helpers fully before editing. New test directories run from `tests/`, matching its existing pytest configuration. Do not reformat unrelated scripts while adding lint coverage.

## Decision diffs

```diff
 # AIClient.analyze and AIClient.model_info
+ if not self._base_url:
+     return None
```

```diff
+ # local-compose.yml ingestion environment
+ API_KEY: ${LOG_GUARDIAN_API_KEY:?Set LOG_GUARDIAN_API_KEY}
+ AI_SERVICE_URL: ""
+ INVESTIGATION_API_KEY: ""
+ KAFKA_ENABLED: "false"
```

Bind API/dashboard to 127.0.0.1 on configurable ports defaulting to 8000/8080. Fail on occupied ports; never stop another process. Document the existing `?api=` override for custom API ports and set CORS to the configured loopback dashboard origins. Avoid fixed container names. No provider keys or investigation-worker service in this profile.

```diff
- connected
+ API connected
+ Latest stored log: <service>, event time <timestamp>, observed by dashboard <time>
```

Fetch the newest log independently with `GET /logs?limit=1`, without severity/anomaly filters. Label event time distinctly from receipt time because `LogResponse` does not expose `created_at`. An idle source is not necessarily disconnected. On API failure retain the last observation and mark it stale. Reuse `textContent` for new untrusted values.

## Steps

- [x] Confirm an issue identifier and create its isolated `feat/<issue>-local-onboarding` worktree. Never implement on main. Keep plans available in that workspace without committing without authorization.
- [x] Add forwarder contract checks first. Cover JSON/INFO fallback, severity aliases, malformed timestamp, Unicode, oversized-line draining, source ownership, URL/key validation, request failures, bounded sequential consumption, child exit, SIGINT, and SIGTERM. Prove failures before adding implementation.
- [x] Implement the forwarder as a standalone stdlib command. Include `--help` with one complete invocation, explicit exit codes, and delivery limitations. Test a real subprocess against a local fake HTTP server so shutdown checks do not only test mocks.
- [x] Add failing disabled-scorer tests, then the empty-base guards. Run the entire ingestion suite. Add and validate the local Compose profile, required-key failure, volume persistence, loopback ports, and absence of model worker/provider credentials.
- [x] Add browser checks before latest-log rendering. Verify malicious message/service strings render as text, filters do not hide source status, and unauthorized or offline responses do not display a healthy connection.
- [x] Add `local-up`, `local-down`, and `test-forwarder` targets. Include forwarder tests in `make test` and the CI matrix; lint the new script and test directory in both local and CI commands.
- [x] Document setup, API-key entry, command invocation, optional port overrides, shutdown, delivery uncertainty, log privacy, disk-growth limits, and cleanup without deleting volumes by default.
- [x] Add a failing stdout-emission test in the demo suite, then emit a flushed JSON record from `emit` before its optional HTTP path. Keep owner-only fault messages on stderr. Keep source containers non-TTY. Pipe the Docker CLI's stdout into the forwarder and leave its stderr separate, never using `stderr=STDOUT`. Verify on the installed Docker version that container stderr remains separate and fault-control diagnostics do not reach stored evidence; stop if that assumption fails. Add the source-only Compose file and exercise both services through separate forwarder processes.
- [x] Execute all verification below against the owner-selected checkout/inventory project. Record this as controlled sandbox onboarding, not external-customer validation.

## Verification

Baseline captured on 2026-09-20, before application edits:

```text
make test: 36 + 200 + 12 + 6 + 47 = 301 passed
make test-demo: 3 passed, 2 warnings
make lint: All checks passed! / 92 files already formatted
```

Raw logs: `/tmp/log-guardian-baseline.EIsuKJ/`. Pytest-asyncio emitted a fixture-loop-scope deprecation warning in the AI suite. Preserve existing warnings; do not fix unrelated code in this milestone.

After implementation run:

```sh
make test
make test-demo
make lint
python3 scripts/forward_compose_logs.py --help
docker compose -f infrastructure/docker/local-compose.yml config
```

Run Chromium checks against a task-owned stack using the repository's browser suite and required URL configuration after reading its setup. Capture screenshots and console/network failures. Use a disposable Compose source to emit structured and plain logs, confirm persistence after API restart, stop the API to verify nonzero forwarder exit, and interrupt forwarding to verify the child exits. Confirm log ingestion works with no provider key and investigation endpoints remain disabled. Then connect the owner-selected checkout/inventory source-only stack. Keep ingestion and source stacks separate. Run the existing scenario without `--capture`, repeat the fault/recovery cycle, and verify stored logs contain checkout timeout and inventory latency messages forwarded from stdout. Record a new local verification artifact; never overwrite preserved bundles or evaluation results.

## Open prerequisites

- Docker availability rechecked: server 29.2.1; no running containers or Compose projects at that check.
- The owner selected checkout/inventory. This resolves the initial source choice, not the later requirement for real-world pilot evidence.
- Issue #31 and its isolated worktree exist. The owner approved native Docker logging; implementation and local verification are complete. Code review, commits, pushes, publication, and any paid execution remain separate actions.

## Excluded

No detector redesign, automatic investigation, spend ledger, notifications, billing, Docker socket mount, durable collector spool, or public deployment. Disk retention remains an explicit local-development limitation until its own milestone. No claims of reliable production collection or paid-product readiness from this work alone.
