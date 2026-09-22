# Vector ingestion feasibility check

## Goal

Determine whether Vector can replace our custom forwarding logic without changing the ingestion API.
Verify exact payloads, authentication, bounded buffering, retries, timestamps and diagnostic exclusion locally.
Produce a measured recommendation, not a production collector release.

## Context

The owner asked whether custom collection is necessary and approved evaluating an existing collector. Recurring detection is paused at 3/6 steps on `feat/33-recurring-incidents`; its uncommitted changes must stay untouched. No commit/push or paid-call authorization is inferred for this spike.

`POST /logs` accepts one object with `service`, `level`, `message`, `timestamp`, authenticated via `X-API-Key`. The API has no ingestion idempotency key. Successful responses are 201. An ambiguous retry may duplicate a stored event.

The demo emits application JSON on stdout and owner-only fault diagnostics on stderr. The existing onboarding test proved Compose log output merges those streams. Reuse native `docker logs` stream separation, not `docker compose logs`.

## Approach

```text
[Selected container stdout] -> [Vector stdin + remap] -> [Disk-buffered HTTP sink]
                                                              |
[Observed records and errors] <- [Disposable API / probe receiver]
```

Run a pinned Vector container, provisionally `timberio/vector:0.54.0-debian`, after confirming the tag exists. Record actual version and image digest. Use Docker already installed; do not install a host agent, change shared services or upgrade dependencies.

Feed stdout from an explicitly selected, non-TTY, task-owned container through a shell pipe. Redirect stderr to a separate owner-only file. Do not mount the Docker socket into Vector. Do not attach to or inject faults into the shared checkout/inventory stack.

Use a bounded persistent disk buffer and a test-only key supplied through environment, never written into evidence. Test a file source separately for checkpoint/restart behavior. A stdin pipe cannot replay bytes lost before buffering; do not call it a durable Docker source or production replacement.

Mapping is strict for this probe: parse JSON, validate all four required fields and allowed levels, preserve offset-aware event time, and replace the output with only the API fields. Malformed data must be dropped with visible diagnostics/counters, not silently repaired. No plain-text fallback in this first probe.

HTTP configuration must send one object, not an array, with `batch.max_events = 1`, JSON encoding and appropriate framing. Verify the actual wire body; documentation alone does not settle framing. Confirm custom `X-API-Key` support and that keys never appear in captured artifacts. Disable irrelevant healthchecks if they do not match our API, without bypassing delivery verification.

Capture retry behavior for 401, 422, 429, 500 and an unreachable receiver. Record which statuses Vector retries versus drops, retry bounds, and observable buffer state. Test buffering through Vector restart using the same volume and a source that remains replayable. Measure duplicates explicitly after an ambiguous response; the current API does not guarantee exactly-once ingestion.

## Sources and reuse

Local sources read: onboarding `app/routes/logs.py`, `app/schemas.py`, `demo/app.py`, and prior native Docker stream verification.

Context7 resolved `/vectordotdev/vector/v0.54.0`. Its HTTP sink examples document JSON encoding, batch sizing and retry controls; docker source excerpts confirm Docker-daemon access and broad default collection. Some retrieved source excerpts are from master, so verify all used syntax against the actual pinned image and version-matched source before execution.

- https://github.com/vectordotdev/vector/tree/v0.54.0
- https://vector.dev/docs/reference/configuration/sinks/http/
- https://vector.dev/docs/reference/configuration/sources/docker_logs/

Reuse the existing ingestion image/API and demo application, not a new storage service or backend adapter. A small stdlib HTTP probe is permitted only to inspect requests and inject HTTP failures; it is a test harness, not collection infrastructure.

## Files and artifacts

| Path | Today | After |
| --- | --- | --- |
| `docs/plans/vector-ingestion-spike.md` | Spike not specified | Reviewed scope and verification gates |
| Task-owned temporary directory: `vector.yaml` | None | Minimal pinned collector configuration, no credentials |
| Same directory: `probe.py`, fixture files, task Compose override | None | Disposable wire/failure tests and isolated local services |
| `docs/vector-ingestion-evaluation.md` | No tested compatibility record | Exact commands, version/digest, configuration, observations and remaining limits |

Do not change the forwarder, runtime API, detector branch or published demo during the spike. Temporary configuration is not a supported product integration until separately reviewed.

## Steps

- [x] Confirm the pinned image/version, inspect its CLI and validate minimal configuration. Create only task-owned containers, ports, volumes and fixtures. Record resources for cleanup. If obtaining the image requires unavailable registry access, report the blocker rather than substituting another version silently.
- [x] Send known JSON through Vector into the probe. Assert a single object per POST, correct auth header, exact service/message/level and equivalent timestamp. Test malformed JSON, invalid severity and missing fields; inspect visible drop/error evidence without exposing credentials.
- [x] Exercise 401/422/429/500, receiver outage and recovery, and persistent-buffer restart. Record attempts, duplicates, buffer limits and failure visibility. Do not claim every error is retried or that all retries are safe.
- [x] Run a task-owned demo/ingestion stack with scoring and investigation disabled. Pipe only selected-container stdout through Vector; generate healthy requests and a fault/reset cycle. Verify stored application records and absence of stderr fault diagnostics. Check API loads and count records through authenticated reads; no UI changes are planned.
- [x] Write the result report with exact versions, commands, expected/actual counts and limits. Recommend adoption only for flows exercised. Stop/remove only task resources. Resume detector work afterward; a permanent collector integration remains a separate reviewed change.

## Decisions

```diff
- Expand scripts/forward_compose_logs.py into a general collector.
+ Evaluate Vector's existing delivery and buffering capabilities.

- Mount the host Docker socket into a third-party container implicitly.
+ Use explicit owner-run stdout piping for this spike; defer daemon access.

- Declare buffering equivalent to lossless, exactly-once delivery.
+ Measure replay/duplicates and document the source and API limits.
```

## Not doing

No permanent install, Docker-daemon privilege grant, customer data, production changes, provider calls, API batch endpoint, custom retry queue, Kubernetes onboarding, source auto-discovery, multiline parser or forwarder deletion. No claim of production readiness from a small controlled probe.

## Review status

Approved in Plannotator; all five experiment steps completed. Results, failures and cleanup are recorded in [the evaluation](../vector-ingestion-evaluation.md). The real-app flow used memory buffering after disk buffering showed unexplained low-volume delivery delays; disk restart recovery was tested separately. This completes the feasibility check, not production adoption.

The owner subsequently authorized committing and pushing only this evaluation and plan on `feat/34-vector-evaluation`, linked to issue #34. Recurring-detector changes remain uncommitted on their separate branch. No paid calls were made. Scratch harnesses and raw evidence remain local under `/tmp/lg-vector-spike/`; this documentation commit does not archive them.
