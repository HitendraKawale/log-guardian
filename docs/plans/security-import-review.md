# Nginx and authentication log review

Issue #48. The owner selected nginx plus structured application authentication logs,
and authorized implementation, verification, commit and push. Continue the existing
business-security direction; no paid model calls, automatic blocking or deployment.
Implemented and locally verified; see ../verification/security-import/README.md.

## Goal

The offline correlation engine exists, but cannot import gateway logs or save a review.
Add explicit nginx/application adapters, authenticated persistent imports and a usable evidence-review page.
Prove the flow with real local HTTP, SQLite/PostgreSQL and Chromium, plus malformed/conflicting inputs.

```text
[Nginx + app JSON] -> [Owner adapters] -> [Correlator]
                                             |
[Review page] <------ [Immutable saved case + evidence]
```

## Decisions

- Owner configuration lives in SECURITY_SOURCES_PATH, never in uploaded event content.
  SECURITY_API_KEY is separate from log/paid-investigation keys; empty disables this API.
- Prescribe a minimal nginx JSON log_format with escape=json, generated request_id,
  time_iso8601, observed remote_addr, status and an owner-mapped route template.
  Forward the generated ID to the application, replacing client X-Request-ID.
- The auth application emits event_id, timestamp, request_id, account_ref and outcome.
  It must obtain request_id through a trusted gateway path. No credential, arbitrary
  message, raw URI/query or forwarding-header field is accepted by either adapter.
- Save normalized evidence, source snapshots, input hashes and a deterministic report.
  Do not retain raw uploaded logs or invent a provider-generated report.
- One source/event identity has one canonical content hash across all saved cases.
  Identical overlap reuses evidence; changed content returns 409, with atomic rollback.
- Mandatory Idempotency-Key binds the upload and owner registry snapshot. Same key and
  content returns the original case; changed content returns 409, including config drift.
- Use two tables, security_cases and security_evidence. A saved bounded report already
  contains the timeline and cited record identities; no separate job queue is needed.
- Keep the API processes free of model execution. GET history/detail remain usable
  even if the current source file changes or becomes unavailable.
- The page keeps its security key in memory, uses text rendering and no automatic
  uploads/retries. It displays the API destination before connection and never follows
  redirects with credentials. Unknown upload outcome retains the idempotency key.

```diff
+ POST /security/cases  # {scope, logs: {registered_source_id: JSONL_text}}
+ GET /security/sources
+ GET /security/cases?limit=25&offset=0  # summaries, not full evidence
+ GET /security/cases/{id}             # frozen report and source snapshot
```

The POST handler authorizes before reading the body, caps the wire body at 2 MiB and
passes at most 1 MiB / 1,000 raw event rows to adapters. Scope stays at four services
and one hour. Sources remain capped at four. Limits reject whole imports; no silent
truncation. Duplicate JSON keys and unsafe values fail with sanitized errors.

## Files

| Files | Today | After |
| --- | --- | --- |
| app/security_adapters.py, tests/test_security_adapters.py | Absent | Strict prescribed nginx/auth formats reuse security_evidence |
| app/config.py, models.py, main.py, routes/security_cases.py | Operational logs and paid investigations | Separate disabled-by-default security import/review API and immutable rows |
| migrations/versions/0007_security_cases.py | Absent | Add case/evidence tables without rewriting operational history |
| tests/test_security_cases.py, tests/test_security_case_migration.py | Absent | Auth, bounded import, idempotency, overlap/conflict, persistence, migration |
| frontend/security.html, security.js, security.css; index.html, app.js | No business-security review | Source/file selection, upload, history, timeline, linked citations and gaps; preserve API override on navigation |
| tests/e2e/test_security_review_ui.py | Absent | Real backend/browser flow and privacy/error/mobile checks |
| tests/integration/test_security_import.py | Absent | PostgreSQL migration and concurrent import checks on a fresh database |
| docs/security-log-review.md and examples/security-review/ | Absent | Reproducible owner config, nginx config, synthetic files and setup |
| Makefile, .github/workflows/ci.yml | Existing suites | Include new browser/integration files in lint; existing suites discover tests |
| evals/tests/test_fresh_report_pilot.py, _fresh_pilot_checks.py | Historical checks import evolving app bytes | Run unchanged checks against verified archived application source in a child; keep live drift guard |
| scripts/export_static_demo.py, tests/e2e/test_static_demo.py | Copy all frontend assets | Exclude the new live uploader from the read-only site |

## Verification and delivery

- [x] Write failing adapter and API checks, then implement the narrow contracts.
- [x] Test whole-import rollback, repeated delivery, changed identities/config, empty
  keys, wrong keys, unknown sources, large/chunked bodies and no paid-investigation rows.
- [x] Test SQLite upgrade from 0006 with existing data; exercise PostgreSQL unique
  constraints and concurrent requests in a new task-owned database.
- [x] Run nginx config validation and a real gateway request, demonstrating that a
  caller's request ID is replaced and query-string data never reaches collected fields.
- [x] Exercise upload/reload/history/evidence/error paths in a real browser; verify
  390px layout and key absence from persistent storage. Preserve screenshots.
- [x] Run affected suites and lint, inspect the diff and prepare the verified milestone for commit/push.

## Not doing

No general-purpose access-log parser, hosted service, continuous collector, model
narrative, attack classifier, account blocking, retention automation or multi-tenancy.
Store source-qualified IDs, not inferred actor identities. Successful authentication
is not proof of compromise. Review-list pagination does not solve indefinite database
retention. Operators must control storage, source configuration and log normalization.
