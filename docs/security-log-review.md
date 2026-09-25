# Review nginx and application authentication logs

Log Guardian can now import a bounded gateway/authentication log window, save its
normalized evidence and review the linked timeline in a browser. This path calls no
model and creates no paid Investigation rows. It reports observed outcomes and gaps,
not an attack verdict, actor identity or proof of AI involvement.

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

All routes require SECURITY_API_KEY in X-API-Key. An empty configured key returns 503;
a missing or incorrect supplied key returns 401. This key is not the operational log
key or the paid-investigation key. One authorized owner can review all stored cases;
this is not multi-tenant authorization.

| Route | Behavior |
| --- | --- |
| GET /security/sources | Current owner source settings and size limits |
| POST /security/cases | Import `{scope, logs}` with a mandatory Idempotency-Key |
| GET /security/cases?limit=25&offset=0 | Saved summaries, at most 50 per page |
| GET /security/cases/{id} | Frozen report, source snapshot and input hashes |

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
predictable values. Protect the database, its backups, input files and report exports.

No continuous collector, automatic retention, production capacity claim, attack
classifier or model narrative is included. The existing investigator does not yet
query these security tables. This milestone adds an evidence-review workflow, not
an autonomous incident verdict. Existing operational log ingestion and agent-recorder
functionality remain available.

## Verification

See [executed verification](verification/security-import/README.md). The checks include
actual nginx header replacement and query-free logging against a synthetic upstream,
PostgreSQL concurrency, SQLite migration and real-API browser uploads.
The application auth fixture is authored; nginx's upstream stub is not a real identity
provider. No customer credentials or account attacks are part of the demonstration.
