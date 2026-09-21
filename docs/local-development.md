# Connect a local Compose project

This installation runs ingestion and the dashboard on your machine. It selects novel error patterns without a trained model. It does not yet detect recurring error spikes, enforce retention, or provide production-grade log delivery.

AI investigations are disabled in this profile. No provider key or paid worker is loaded. The application-log workflow does not use the BGL classifier; stored records show `unscored` rather than invented scores.

## Start Log Guardian

Requirements: Docker Compose v2 and Python 3.11 or later. The forwarder uses only the Python standard library.

```sh
export LOG_GUARDIAN_API_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
make local-up
```

Keep this key in your password manager for restarts. Do not commit it. Enter the same key in the dashboard's API key field at <http://localhost:8080/?api=http://localhost:8000>. The browser stores this log key in localStorage; use a trusted browser profile. It cannot authorize paid investigations.

The API listens at <http://localhost:8000>. Both published ports bind to loopback only. Missing `LOG_GUARDIAN_API_KEY` prevents startup. An occupied port causes startup to fail; do not stop someone else's service.

To choose different ports, set `LG_API_PORT` and `LG_DASHBOARD_PORT` before `make local-up`. Open the selected dashboard port with `?api=http://localhost:<api-port>` and pass the same API origin to the forwarder. The Compose profile configures CORS for those localhost and 127.0.0.1 dashboard origins.

## Connect one service

Run your application normally, then start one forwarder per selected service from this repository:

```sh
python3 scripts/forward_compose_logs.py \
  --file /absolute/path/to/your/compose.yml \
  --project-name your-compose-project \
  --service checkout \
  --api-url http://127.0.0.1:8000
```

Use the project name shown by `docker compose ls`. Repeat `--file` for override files. The command inherits `LOG_GUARDIAN_API_KEY`; never pass the key as an argument. Docker access stays with the owner-run CLI; no Docker socket is mounted into Log Guardian.

The default stored service name is `your-compose-project/checkout`. Use `--source-name checkout` only when you deliberately want a different identity. The selected source owns that identity, even if a log message claims another service.

The command resolves exactly one running container, rejects TTY mode, and follows native `docker logs` to keep stdout and stderr separate. It rejects scaled services with multiple containers. Compose's `logs` command merges the streams and is deliberately not used for collection. Restart the collector after a source container stops or is replaced; it does not switch containers automatically.

The command starts at new output, not historical logs. Start it before generating traffic. Each successful POST prints an acknowledgement count and timestamp to stderr. Rejected malformed or oversized records increment a separate counter. Ctrl+C stops the owned Docker CLI child as well as the forwarder.

In the dashboard, open Logs. `API connected` means the API answered, not that the collector is running. `Latest stored log` shows the source, event time, and when this browser first observed that record. Filters do not hide this observation. An idle application can remain healthy without producing new logs.

## Accepted log formats

Docker's timestamp prefix becomes the event time; application-supplied timestamps cannot override it.

```json
{"level":"ERROR","message":"inventory request timed out"}
```

- JSON objects with a nonempty string `message` use their `level`, defaulting to INFO when absent. Level matching ignores case; WARN maps to WARNING and FATAL to CRITICAL. An invalid provided level rejects the record.
- Plain text and malformed JSON remain literal messages. A leading `ERROR`, `ERROR:`, or `[ERROR]` token sets severity. A word such as `error` in the middle of a message does not.
- Invalid UTF-8 becomes replacement characters. Missing or invalid Docker timestamps reject the record.
- Lines longer than 64 KiB are drained and rejected once, not split into fabricated events. Multiline stack traces remain separate events.
- The collector reads Docker stdout only. Container stderr is not ingested by this initial collector. Use structured stdout logs in non-TTY containers. Docker diagnostics remain on stderr.

## Verify with checkout and inventory

The source-only profile runs the existing demo applications without direct API ingestion. It therefore exercises the collector rather than bypassing it. Application records go to stdout; owner-only fault diagnostics stay on stderr.

```sh
docker compose -f infrastructure/docker/onboarding-source-compose.yml up -d --build
```

In two terminals, with the log key exported in each:

```sh
python3 scripts/forward_compose_logs.py \
  --file infrastructure/docker/onboarding-source-compose.yml \
  --project-name log-guardian-source --service checkout --source-name checkout

# Run separately, not after the long-running checkout command:
python3 scripts/forward_compose_logs.py \
  --file infrastructure/docker/onboarding-source-compose.yml \
  --project-name log-guardian-source --service inventory --source-name inventory
```

After both print `following`, run the fault/recovery scenario from another terminal:

```sh
.venv/bin/python demo/run_scenario.py
```

The scenario uses the default ports 8000, 9001, and 9101. It does not need the log key unless exporting logs; do not use its legacy `--capture` option against this authenticated profile. It injects an inventory delay, checks real checkout 504 responses, resets the delay in `finally`, and checks recovery. Review `checkout` and `inventory` in Logs. Repeat the scenario to verify collection through another fault/recovery cycle. The current novelty detector does not promise a new candidate for that recurrence.

This controlled sandbox verifies integration, not detection accuracy on customer logs.

## Delivery, privacy, and limits

The collector sends one request at a time with a five-second timeout. It reads the next line only after the current request completes. Pipe backpressure bounds collector memory; Docker's log retention may still discard old data. There is no durable spool, retry, automatic reconnect, or exactly-once guarantee.

Any delivery failure stops the command with exit 1. The current record may already have persisted when the response was lost. Manual replay can duplicate records; restarting with the default `--tail 0` also misses records emitted while disconnected. Fix the connection and restart explicitly. Exit 2 means invalid configuration; 130 and 143 mean SIGINT and SIGTERM.

Treat ingested messages as sensitive. Raw application logs are stored locally, not automatically redacted before storage. Do not forward passwords, tokens, customer records, or other data you cannot retain. AI execution is disabled, but this does not make raw log storage safe for secrets.

SQLite data persists in the Compose volume. No automatic retention or disk quota is implemented yet. Monitor disk use and limit this release to development traffic. This is not a production logging replacement.

## Troubleshooting and shutdown

- `API offline or unauthorized`: check the API URL, browser key, and `docker compose -f infrastructure/docker/local-compose.yml logs ingestion-service`.
- No new logs: confirm the exact project/service, that the application emits stdout without a TTY, and that traffic occurred after collection started.
- No candidates: the current detector observes 500 logs before trusting novelty, considers ERROR/CRITICAL by default, and does not raise repeat incidents for familiar templates. Candidate detection changes are a separate milestone.
- `unscored`: expected here. The domain-specific classifier is intentionally disabled.

Stop each forwarder with Ctrl+C, then:

```sh
make local-down
docker compose -f infrastructure/docker/onboarding-source-compose.yml down
```

These commands keep the local data volume. Do not add `--volumes` unless you intend to delete stored logs.
