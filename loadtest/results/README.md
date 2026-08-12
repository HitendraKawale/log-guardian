# Load test results

Committed so the throughput numbers in the docs have a method attached. Rerun
with `make loadtest` and replace both files.

## 2026-08-12

**Method.** `make loadtest`, which runs `loadtest/k6.js` in the `grafana/k6`
container against the Compose stack on the same machine. Two scenarios in
parallel for 20s each: 10 VUs on `POST /logs` (synchronous, so each request
waits on the AI service) and 10 VUs on `POST /logs/stream` (publishes to Kafka
and returns).

**Hardware.** Apple M1, 8 cores, 16 GB, macOS 26.5.1, Docker 29.2.1. Everything
— load generator, both services, Postgres, Kafka, Prometheus, Grafana, Jaeger —
on one laptop, so these are contention numbers, not headroom numbers.

**Result.**

| metric | value |
| --- | --- |
| requests | 3,869 |
| throughput | 190.9 req/s |
| failed | 0.00% (0 of 3,869) |
| checks passed | 3,869 of 3,869 |
| median latency | 19.4 ms |
| p90 | 98.2 ms |
| p95 (all) | 120.0 ms |
| p95 (stream only) | 52.2 ms |
| max | 393.1 ms |
| anomalies flagged | 469 |

Both thresholds in the script held: `http_req_failed < 1%` and stream
`p(95) < 200ms`.

**Reading it.** The streaming path is roughly 2.3× faster at p95 (52 ms against
120 ms overall) because it returns as soon as Kafka accepts the message, while
the synchronous path blocks on an HTTP round trip to the scorer. That gap is the
entire argument for having built the streaming path, and it is the number to
quote when asked why.

The tail is wide — 19 ms median against a 393 ms max — which is what you would
expect from everything sharing eight cores with a JVM-based broker and a tracing
collector. Worth re-running on separated hosts before drawing any conclusion
about the services themselves.

## Files

- `k6-summary.json` — machine-readable metrics, `--summary-export` output
- `k6-run.txt` — the full console report
