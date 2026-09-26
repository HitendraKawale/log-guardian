# Review nginx and application authentication logs

Log Guardian can now import a bounded gateway/authentication log window, save its
normalized evidence and review the linked timeline in a browser. Importing calls no
model and creates no paid Investigation rows. A separate, explicit action can queue
an AI investigation of that saved case. Its output is an unverified draft, not an
attack verdict, actor identity or proof of AI involvement.

## Local setup

Use a checkout containing the security-import milestone. From the repository root,
with the shared `.venv` installed, set owner configuration and a separate security key:

```bash
export SECURITY_SOURCES_PATH="$PWD/examples/security-review/sources.json"
export SECURITY_API_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export CORS_ALLOW_ORIGINS=http://127.0.0.1:8481
cd services/ingestion-service
../../.venv/bin/python -m alembic upgrade head
../../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8480
```

In another terminal, from the repository root:

```bash
python3 -m http.server 8481 --bind 127.0.0.1 --directory frontend
```

Open `http://127.0.0.1:8481/security.html?api=http://127.0.0.1:8480`.
Use unused ports if these are occupied; do not stop another application's server.
Set matching API/CORS URLs if you change them. Production deployments should use an
explicit CORS allowlist and TLS. The page refuses non-loopback plain HTTP and does not
follow credential-bearing redirects. The operational dashboard links to Security review.

Enter the SECURITY_API_KEY from your first terminal and click Connect. The page keeps
it in memory, not localStorage or sessionStorage. A page reload requires entering it
again. The old operational dashboard's log-key behavior is unchanged.

For the authored example:

1. Set From to `2026-09-01T10:00:00Z` and To to `2026-09-01T10:10:00Z`.
2. Select `examples/security-review/nginx.jsonl` for edge.
3. Select `examples/security-review/auth.jsonl` for auth.
4. Click Save review. Expect three linked requests, two failures and one success.
5. Open a citation to inspect its record, then reload and reconnect to inspect history.

These six records are synthetic development fixtures with documentation-range IPs.
They are not captured customer traffic. Gateway HTTP 200 deliberately coexists with
an authentication failure: the importer does not infer auth success from HTTP status.

## Produce the supported log formats

The nginx configuration is in `examples/security-review/nginx.conf`. Include it in the
nginx `http` context, configure the upstream address for your deployment, and validate
with `nginx -t` before enabling it. It is a logging/reverse-proxy example, not a complete
TLS or deployment security configuration.

It uses [log_format escape=json](https://nginx.org/en/docs/http/ngx_http_log_module.html)
and [proxy_set_header](https://nginx.org/en/docs/http/ngx_http_proxy_module.html).
Nginx's [$request_id](https://nginx.org/en/docs/http/ngx_http_core_module.html#variables)
is a request identifier generated from random bytes. The gateway overwrites the client
X-Request-ID before forwarding. A URI map emits only owner-specified route names,
with `/other` as the fallback. Raw request URLs, queries and request bodies are not logged.

```json
{"time":"2026-09-01T10:00:02+00:00","request_id":"r1","remote_addr":"192.0.2.1","status":"200","route":"/login"}
```

The nginx adapter uses request_id as its event identity. An identical reimport deduplicates;
changed content under the same source/request ID is a conflict, not a replacement.
Configure one source identity per stable logging stream, and do not silently reuse it
for an unrelated application or a different source-trust policy.

The application emits a separate JSON line after its authentication decision:

```json
{"event_id":"a1","timestamp":"2026-09-01T10:00:01Z","request_id":"r1","account_ref":"account-1","outcome":"failure"}
```

The application supplies a unique event_id and an explicit outcome of success, failure
or unavailable. request_id and account_ref may be null. Do not record passwords,
email addresses, tokens or exception messages. Use a stable pseudonymous account_ref.

Only trust the propagated request ID if the application is reachable exclusively
through the trusted gateway, or has equivalent authenticated ingress enforcement.
Do not trust arbitrary request headers on a publicly reachable application. The import
cannot verify your network topology. A shared request namespace is an owner assertion,
not cryptographic provenance.

The nginx format observes `$remote_addr`. If your deployment uses the real-IP module,
its trusted proxy configuration changes what this means. Review that configuration;
the importer does not discover it, trust X-Forwarded-For or identify people from IPs.

Existing combined-format nginx logs and arbitrary application JSON are not supported.
Unknown fields fail validation rather than being silently discarded. Install the
prescribed formats or deliberately normalize an existing export before import.

## Owner source registry

SECURITY_SOURCES_PATH points to a local JSON file, capped at 16 KiB. Its example contains
an edge nginx source and an auth application source. Each entry defines source_id,
service, event_kind, format and optional request_namespace. Uploaded logs cannot define
or override these values. A wrong format/event_kind pairing disables loading the registry.

Source namespaces may be shared only where generated IDs propagate across those
services. Leave the namespace null if that guarantee is absent. Those records remain
visible but unlinked. A source-qualified event ID remains independent from a
cross-service request key.

The registry is read for each import and saved with the case. Existing history remains
readable even if the current registry changes or becomes unavailable. Changing source
semantics under an already stored event identity produces a conflict. Register a new
source identity for a genuinely new stream, rather than relabeling old evidence.

## API contract

All /security routes require SECURITY_API_KEY in X-API-Key. An empty configured key returns 503;
a missing or incorrect supplied key returns 401. This key is not the operational log
key or the paid-investigation key. One authorized owner can review all stored cases;
this is not multi-tenant authorization.

| Route | Behavior |
| --- | --- |
| GET /security/sources | Current owner source settings and size limits |
| POST /security/cases | Import `{scope, logs}` with a mandatory Idempotency-Key |
| GET /security/cases?limit=25&offset=0 | Saved summaries, at most 50 per page |
| GET /security/cases/{id} | Frozen report, source snapshot, input hashes and optional linked investigation ID |

`scope` has services, start and end, with aware timestamps and a positive window of at
most one hour. Its services must exactly match the configured source services. `logs` maps
each configured source ID to its JSONL text. Supply an empty string for a source with
no evidence. That means missing evidence, not healthy operation.

The wire request is capped at 2 MiB, decoded event input at 1 MiB, raw records at 1,000
before deduplication, and each line at 16 KiB. There are at most four sources and four
scoped services. The existing normalized-evidence limit also applies after conversion.
Oversized wire input returns 413. Malformed, over-limit decoded or out-of-scope evidence
returns 422 without echoing its content. The importer rejects the whole request.

Use one stable Idempotency-Key per upload. Repeating the same payload and owner registry
returns the saved case with 200. A new case returns 201. Changed payload or configuration
under that key returns 409. JSON object key ordering outside the log strings does not
matter; changes to the log strings do. The page preserves its key for an unchanged retry
while it stays open, and never retries automatically. If the page is closed after an
uncertain response, inspect history before uploading again with a new key.

Overlapping imports with new keys may create separate reviews while reusing identical
source/event records. Conflicting content for any stored identity returns 409 and rolls
back the entire transaction, including newly introduced evidence in that request.
Database uniqueness handles concurrent imports on SQLite and PostgreSQL.

## Optional AI investigation

Configure a distinct INVESTIGATION_API_KEY for the API and worker. An empty key disables
execution endpoints. The review key cannot queue a run, read its report/events or cancel
it. The linked run ID is visible to reviewers, but it is not an execution capability.
Both keys stay in page memory. Changing the API endpoint clears the execution key.

After inspecting a saved review, enter the investigation key, acknowledge provider
sharing and choose Start or open investigation. Uploading, opening history and reloading
the page never queue work. The control calls:

```text
POST /investigations/from-security-case/{case_id}
X-API-Key: the separate investigation key
```

The route accepts no scope, question or system overrides. It copies the saved scope,
uses a fixed question and queues system C. Creation returns 201; repeated requests
return the same run with 200. The database enforces one run per saved case, including
failed or cancelled runs. Reopening is not a paid retry. Separately imported cases can
still get separate runs, even when their underlying events overlap.

Upgrade the API and worker together before enabling case execution. Saved security runs
carry an internal S discriminator, which old workers reject before provider dispatch
instead of interpreting them as ordinary operational C runs. The updated worker verifies
the case binding and executes the existing C algorithm; the public API reports C.
An old worker may fail such a run, so stop old workers before queueing cases.

The worker must run separately with the same database and INVESTIGATION_API_KEY. Its
existing command is `python -m app.investigator` from services/ingestion-service, using
the repository environment. OPENAI_API_KEY enables its provider client. Do not start a
live worker against queued cases without current spending authorization. This milestone
was verified with httpx.MockTransport only; old research allowances do not authorize a
live check. No live worker was started for this implementation.

The worker verifies the saved snapshot binding before contacting a provider. It uses
only the case's frozen evidence, not today's source registry, operational logs with
similar service names, other cases, metrics or runbooks. Missing/inconsistent source
state fails the run rather than falling back to a broader source.

The model sees only read_security_evidence, with offset and limit arguments. A bounded
initial page is delivered before its first request and recorded in the existing tool
journal. Every page carries whole-case counts, explicit gaps and a contiguous timeline
page with next_offset. Pagination never converts unknown collection completeness into
complete capture. Partner references do not authorize citations to undelivered records.

Existing worker limits remain: six provider requests, eight tool executions including
the initial read, 16 KiB per result, 64 KiB total evidence, 120 seconds and 1024 output
tokens. The worker uses a $0.025 per-run allowance and disables SDK retries. That estimate
is not a provider billing guarantee or account-wide cap. The existing pending-queue
check is not a strict global ceiling under concurrent different-case submissions.
Large cases can exceed evidence/cost limits before the model reads every record.

The page displays status, missing evidence and the model draft, with links to the tool
snapshots actually delivered. Cancel investigation requests cancellation through the
existing endpoint. A provider request already in flight may still be billed. Partial
evidence remains available after failure. Missing/ambiguous provider usage stays unknown.

Every draft needs human review. Citation validation checks delivered membership, not
whether a quote supports a claim. The experimental offline verifier is not in this path.
Successful authentication still does not prove compromise; addresses and timing do not
prove shared actors, coordination or AI automation. Security-case fields can contain
attacker-controlled strings even when their source configuration is owner-controlled.

## Evidence, privacy and limits

The saved report includes normalized source timestamps, auth outcomes, observed address
and account-reference counts, exact-ID links, ambiguous groups and unlinked records.
Two auth results for one request do not become one invented outcome. A timestamp order
is a display order, not proof of causality. Every case retains unknown collection
completeness and unestablished impact/attribution.

Stored data includes normalized records, source configuration, report and raw-input
SHA-256 hashes. It does not retain raw uploaded lines, but addresses, routes, account
references and request IDs can still be sensitive. Hashes bind content; they do not
prove source authenticity, prevent a database administrator changing it, or anonymize
predictable values. Protect the database, its backups, worker logs, input files and report exports.

No continuous collector, automatic retention, production capacity claim or validated
attack classifier is included. The optional investigator produces drafts for review,
not autonomous incident verdicts. Existing operational log ingestion and agent-recorder
functionality remain available. Enabling provider execution shares normalized evidence,
including potentially sensitive addresses and account references, outside this database.
Investigation reads carry Cache-Control: no-store, as security review responses do.

## Verification

See [executed verification](verification/security-import/README.md). The checks include
actual nginx header replacement and query-free logging against a synthetic upstream,
PostgreSQL concurrency, SQLite migration and real-API browser uploads.
The application auth fixture is authored; nginx's upstream stub is not a real identity
provider. No customer credentials or account attacks are part of the demonstration.

The [investigator connection checks](verification/security-investigator/README.md)
cover case isolation, first-request evidence delivery, durable tool intent, byte-bounded
pagination, permission separation and the scripted-worker browser flow. They do not
measure a real model's security-diagnosis accuracy.
