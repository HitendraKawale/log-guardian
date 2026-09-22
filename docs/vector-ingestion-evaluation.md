# Vector ingestion evaluation

## Verdict

Vector can ship our structured application logs without an ingestion API change.
The tested memory-buffered configuration passed the real fault/recovery flow.
Do not replace the supported forwarder yet: low-volume disk buffering showed an
unexplained delay, and stdout piping is not durable container lifecycle tracking.

The spike is complete, including recording failed checks. Permanent integration
needs its own review. No production collector configuration was installed.

## Version and isolation

```text
vector 0.54.0 (aarch64-unknown-linux-gnu 2b8b875 2026-03-10 15:47:37.284215410)
timberio/vector:0.54.0-debian
sha256:099732c890b095d5222f59bdc82a0579ae3d48b9e2407f3680586dd8d2f75f64
```

Scratch configuration, harnesses and evidence: `/tmp/lg-vector-spike/`.
All containers used the task-owned `lg-vector-spike` network. No Docker socket
was mounted, host agent installed, customer logs sent or paid model called.

The real API ran at `http://127.0.0.1:18334`. Portless registered an alias, but
its proxy was not running, so the check used that recorded fallback port rather
than changing a shared proxy. Both `/health` and authenticated `/logs` responded.
The fallback URL is now stopped; the temporary alias was removed.

All task containers, the task disk-buffer volume and network were removed after
capturing logs. The downloaded Vector image and scratch evidence remain.
The four original onboarding/source containers remain running and unchanged.
The recurring-detector branch was not edited during the spike.

## Exact encoding and limits

The working sink settings were:

```json
{
  "type": "http",
  "method": "post",
  "encoding": {"codec": "json"},
  "framing": {"method": "bytes"},
  "batch": {"max_events": 1, "timeout_secs": 1},
  "request": {
    "headers": {"X-API-Key": "${LG_SPIKE_KEY}", "Content-Type": "application/json"},
    "concurrency": 1,
    "timeout_secs": 2,
    "retry_attempts": 3,
    "retry_initial_backoff_secs": 1,
    "retry_max_duration_secs": 2
  },
  "buffer": {"type": "memory", "max_events": 100, "when_full": "block"},
  "healthcheck": {"enabled": false}
}
```

Actual complete configurations, including inputs, URI and strict VRL mapping,
are `vector.json`, `compare-{disk,memory}.json`, `http-trials.json` and
`live-vector.json` in the scratch directory. The disk variant used
`max_size=268435488` bytes and `when_full=block`, with acknowledgements enabled
for its file source. The stdin/memory live variant disabled acknowledgements.
Buffer-full behavior was configured but not stress-tested.

Mapping accepts structured JSON only, requires all four API fields, validates
severity and an offset-aware timestamp, and emits exactly those fields. Invalid
records are dropped with visible diagnostics. Plain text and multiline input
were not evaluated. The API has no ingestion idempotency key.

## Observed results

| Check | Result |
| --- | --- |
| Image version and configuration validation | Passed |
| Exact body and authentication | Two valid single-object POSTs; exact service/message/level and timestamp string |
| Invalid JSON, severity, missing fields, naive timestamp | Four records excluded; mapping/drop diagnostics visible |
| HTTP 401 / 422, memory buffer | One attempt each, then explicit non-retriable drop |
| HTTP 429 / 500, memory buffer | Four attempts each, then retry exhaustion/drop |
| Receiver accepts then disconnects without response | Same event delivered four times, demonstrating duplicate risk |
| Short receiver outage, memory buffer | One test event delivered after receiver restart |
| Persistent disk-buffer restart | Ten expected records recovered, ten deliveries, no duplicates in this trial |
| Low-volume disk delivery | Failed the eight-second observation deadline; unresolved |
| Real healthy/fault/recovery flow, memory buffer | 200, then actual deadline 504, then 200; fault reset in finally |
| Real API records | All nine stdout records stored exactly once in this trial; fields and UTC instants matched |
| Fault diagnostics | Present in separately captured stderr, absent from stored evidence |
| API authorization and spending defaults | Unauthenticated logs returned 401; investigation API returned 503; all logs unscored |

HTTP statuses were injected by the stdlib probe. Real-API authentication was
checked separately. The probe archives auth-equality booleans, never header
values. Keys used in the spike were disposable test strings.

### Disk delay and comparison

The original disk-buffered failure harness timed out after 35 seconds waiting
for a 422 barrier record. The receiver remained responsive to a direct GET and
Vector's file checkpoint advanced to the end of the missing records. Two pending
records arrived only when Vector shut down, then received non-retriable 422s.

A separate comparison used fresh state directories and identical staged input:
- Disk: zero of the first three records observed within eight seconds.
- Memory: three successive batches of three records delivered in approximately
  0.103, 0.102 and 0.104 seconds, including the polling interval.

The comparison changes buffer type and its fresh state directory; it identifies
a disk-path problem in the tested setup, not the internal cause or a general
Vector defect. Disk and memory runs used a host bind mount for fresh state;
the original delay also occurred with a Docker volume.

A subsequent same-volume restart trial recovered all ten pending test records
once after receiver recovery. This proves that specific restart sequence, not
losslessness across arbitrary failures. Low-volume delivery latency remains a
reason not to adopt the tested disk configuration yet.

### Real application flow

Two task-owned non-TTY containers ran the existing checkout/inventory demo.
Native `docker logs --follow` stdout fed separate Vector stdin containers;
stderr went to owner-only scratch files. The API used the existing onboarding
image with `AI_SERVICE_URL` and `INVESTIGATION_API_KEY` empty and Kafka disabled.
No forwarding path granted Vector Docker-daemon access.

One healthy checkout, one injected two-second inventory delay causing a genuine
one-second checkout timeout, and one recovered checkout produced six checkout
records and three inventory records. All nine matched stored records, including
the delayed inventory completion. Fault-control warnings were excluded.

The first comparison assertion incorrectly interpreted SQLite's naive returned
timestamps as host-local time. The final check explicitly treats them as UTC,
matching the ingestion contract; it then passed without rerunning the fault flow
or sending duplicate source traffic. This was a harness correction, not an API
or collector fix.

## Commands and evidence

Executed checks:

```sh
docker run --rm timberio/vector:0.54.0-debian --version
docker run --rm -e LG_SPIKE_KEY=spike-test-only \
  -v /tmp/lg-vector-spike:/spike:ro \
  timberio/vector:0.54.0-debian validate --no-environment /spike/vector.json
python3 /tmp/lg-vector-spike/check.py
python3 /tmp/lg-vector-spike/failures.py       # initial timeout retained
python3 /tmp/lg-vector-spike/compare.py
python3 /tmp/lg-vector-spike/http_trials.py
python3 /tmp/lg-vector-spike/disk_restart.py
docker exec lg-vector-probe python /spike/live_flow.py
python3 /tmp/lg-vector-spike/verify_live.py
```

The live collector command, repeated for checkout and inventory, was:

```sh
docker logs --follow lg-vector-checkout 2>/tmp/lg-vector-spike/checkout-stderr.log |
  docker run --rm -i --name lg-vector-live-checkout --network lg-vector-spike \
    -e LG_SPIKE_KEY=vector-local-test -v /tmp/lg-vector-spike:/spike:ro \
    timberio/vector:0.54.0-debian --config /spike/live-vector.json
```

These commands describe the executed scratch experiment, not a turnkey installer;
its containers and volumes have been cleaned up.

Relevant outputs:

```text
PASS: 2 valid single-object POSTs, exact fields/auth/timestamps; 4 invalid records excluded
PASS: healthy 200 -> injected deadline 504 -> recovery 200; fault reset
PASS: 9/9 stdout records stored once; exact fields and equivalent UTC timestamps; stderr fault diagnostics excluded; scoring off; investigation API disabled; log authentication enforced
```

Artifacts:
- `http-results.json`: status attempts, disconnected-response duplicates and short-outage result.
- `comparison-results.json`: disk/memory observation deadlines and timings.
- `disk-restart-results.json`: ten expected/received records and attempt counts.
- `requests.jsonl`: probe observations across all experiments, including failures.
- `live-stored-records.json`, `{checkout,inventory}-stdout.jsonl`: source/storage comparison.
- `*-stderr.log`: separately captured Docker stderr, including owner fault diagnostics.
- `lg-vector-*-final.log`, `failure-run.log`, `http-trials-run.log`: operational evidence.
- `live-image-ids.txt`: exact existing API/demo image IDs.
- `checkpoints.json`: original pre-shutdown checkpoint.

The file source warned that an initially empty file was too small to fingerprint;
it started once fixtures were appended. Mapping/drop logs are rate-limited, so
log-line counts are not reliable drop counts.

## Product decision

Do not build another general-purpose collector. Vector's mapping and HTTP delivery
fit this API and passed the controlled memory-buffered application flow.

Keep the existing forwarder supported for now. Before a permanent Vector option:
1. Resolve or avoid the measured disk-buffer latency with evidence, not a silent
   switch to another version.
2. Choose the supported source lifecycle and permissions: stdin piping is an
   owner-run bridge, not automatic restart/replay handling.
3. Define duplicate handling and acceptable loss during extended outages. Finite
   retries drop records; ambiguous responses can duplicate them.

No benchmark, production reliability, sustained throughput or exactly-once claim
follows from this spike. Resume recurring incident detection next; do not expand
custom collection while the remaining Vector issues are investigated separately.

References:
- https://github.com/vectordotdev/vector/tree/v0.54.0
- https://vector.dev/docs/reference/configuration/sinks/http/
- Approved scope: `docs/plans/vector-ingestion-spike.md`
