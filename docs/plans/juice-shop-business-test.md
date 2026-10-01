# Juice Shop business test

Status: complete. All five final business cases and archive verification passed. The local inspection services remain running; upstream test and WebSocket limitations are preserved. No commits, pushes or paid calls occurred.

For execution: use `executing-plans` and an isolated Log Guardian worktree. Keep the external shop at `/Users/hitesh/juice-shop`. No subagent tools are available.

## Goal

Replace authored authentication fixtures with events emitted by a running shop during browser actions.
Verify that the existing no-model assessment describes those records correctly and preserves missing evidence.
Prove it with correlated logs, browser observations, cited assessments and reproducible checks, not an attack-accuracy claim.

## Scope and source

The user selected the local business test and previously authorized cloning the shop under home. This is a local experiment, not a production deployment or an upstream contribution.

- Log Guardian baseline: merged PR #53, `d150fac52414cf0ede06bc20443dc199dd094df6`. Resolve origin/main again before creating the worktree; do not silently adopt a different application revision.
- External source: `https://github.com/juice-shop/juice-shop`, release `v20.2.0`, commit `5658473cf8814459bf89000ce373b20ed0b4eb37`, MIT.
- Clone exists, detached at that commit, with no dependency install or source edits yet.
- Docker server reports `29.2.1`; Node reports `v26.7.0`. Build the shop in containers rather than installing its intentionally vulnerable dependencies into the host environment.
- The official root Dockerfile is the starting point. Do not use the upstream intentionally insecure infrastructure templates. Record resolved image IDs/digests and lockfile hashes; do not claim bit-for-bit reproducible dependency resolution.
- Portless has no active routes. Do not start or change the shared proxy. Ports 8490, 8491 and 8492 were free during inspection; recheck before launch and persist any replacement ports in the task runtime manifest.

## One flow

```text
[Browser scenarios] -> [nginx] -> [Juice Shop]
                          |          |
                          +----+-----+
                               v
                    [Bounded real log exports]
                               |
                               v
                    [Log Guardian assessment]
```

Before: Log Guardian's prior business cases contain authored auth records.
After: nginx generates request IDs and access records; the application emits explicit outcomes at its actual login decision branches. The driver never manufactures auth evidence from planned actions or HTTP status.

## Decisions

### Keep the product unchanged

Use the existing registry, import endpoint, saved-case browser and deterministic assessment. Do not build a new collector, parser, model workflow or monorepo integration. Only add a maintained product change if the experiment exposes a reproduced defect; stop to review that change separately.

The lab lives under `/tmp/lg-juice-business/`. Preserve reviewed scripts/configuration as evidence under `docs/verification/juice-shop-business/`, with scripts suffixed `.py.txt` where appropriate. This is an experiment archive, not a new automatically collected CI suite.

| File | Today | After |
| --- | --- | --- |
| `~/juice-shop/routes/login.ts` | Password decision, MFA-required response and session issuance; no compatible audit events | Small opt-in calls at those decisions; authentication behavior unchanged |
| `~/juice-shop/lib/securityAudit.ts` | Absent | Bounded JSONL auth-event writer using Node built-ins; no response bodies, credentials or tokens |
| `~/juice-shop/test/server/securityAudit.unit.test.ts` | Absent | Node tests for the recorder's schema, pseudonyms, request IDs, disabled mode and failure handling |
| `/tmp/lg-juice-business/{compose.yml,nginx.conf,sources.json}` | Absent | Isolated shop/gateway runtime and owner registry matching existing importer formats |
| `/tmp/lg-juice-business/run.py` | Absent | Browser actions, bounded export/import, independent assertions and sanitized evidence capture |
| `docs/verification/juice-shop-business/` in the new Log Guardian worktree | Absent | Source pin, patch, reproducible scripts, configuration, outcomes, screenshots and hashes, excluding runtime credentials |

### Record application decisions, not status guesses

Inspection: `routes/login.ts` registers a session through `security.authenticatedUsers.put` before returning an authentication object. Invalid credentials take a separate branch. MFA-required requests return 401 without completing authentication. `routes/2fa.ts` has its own completion flow; it is outside this first experiment.

The intended route changes are these additional calls, not a replacement login implementation:

```diff
+import { auditAuth } from '../lib/securityAudit'
 ...
 security.authenticatedUsers.put(token, authenticatedUser)
+auditAuth(res.req, 'success', user.email) // vuln-code-snippet hide-line
 res.json({ authentication: { token, bid: basket.id, umail: user.email } })
 ...
 if (user.data?.id && user.data.totpSecret !== '') {
+  auditAuth(req, 'unavailable', user.data.email) // vuln-code-snippet hide-line
   res.status(401).json({ status: 'totp_token_required', ... })
 ...
 } else {
+  auditAuth(req, 'failure', req.body.email) // vuln-code-snippet hide-line
   res.status(401).send(res.__('Invalid email or password.'))
 }
```

The ellipses above omit unchanged code, not implementation choices. Leave SQL, session creation, responses and intentional vulnerabilities unchanged. Follow the shop's AGENTS.md and run its Refactoring Safety Net; do not update challenge fixes/caches simply to suppress a failure.

`auditAuth` emits only the existing `application_auth_json` fields:

```json
{"event_id":"generated UUID","timestamp":"server UTC timestamp","request_id":"gateway-generated ID","account_ref":"HMAC pseudonym","outcome":"success|failure|unavailable"}
```

- Outcomes come from literal call sites, not the supplied email or an HTTP response code.
- Success uses the resolved account email. Failure uses the attempted account email. These are not proof of a person's identity. Non-string/overlong identities become null; never stringify arbitrary request objects.
- HMAC pseudonyms use a per-lab random key, the same key for all cases. Do not archive that key. Do not log plaintext emails, passwords, session tokens or exception details.
- Read only a single validated 32-character hexadecimal gateway request ID; reject malformed/multi-valued IDs as null. The private network is the trust boundary, not the string format.
- Opt-in file path/key configuration leaves unconfigured upstream behavior unchanged. A write failure emits a fixed diagnostic without request content; the driver treats any diagnostic or missing expected event as test failure. Do not swallow a recorder failure and call the result a complete capture.
- Do not fabricate an auth failure for a database/server error. Missing events remain missing and fail a scenario that expected a completed decision.

### Use a private gateway and bounded collection

Adapt the existing `examples/security-review/nginx.conf` without logging raw URLs, queries, headers or bodies:

```diff
 map $uri $security_route {
     default /other;
-    /login /login;
+    /rest/user/login /login;
+    /rest/products/search /catalog;
+    /api/BasketItems/ /cart;
 }
 ...
 proxy_set_header X-Request-ID $request_id;
-proxy_pass http://127.0.0.1:9000;
+proxy_pass http://shop:3000;
```

Publish only nginx on loopback, initially `127.0.0.1:8490`. Do not publish the shop's port. Use a task-named internal Docker network so the running shop cannot contact external services. No privileged containers, Docker socket mounts or home-directory mounts. Builds may download dependencies; runtime receives no provider credentials. Block browser requests outside the lab origins and record unexpected attempts without storing credentials.

Serve Log Guardian's unchanged API/frontend on loopback, initially 8491/8492, with a new SQLite database and a distinct review key. Set `OPENAI_API_KEY`, `INVESTIGATION_API_KEY`, `OTEL_CONSOLE` and `OTEL_EXPORTER_OTLP_ENDPOINT` empty. Start no worker. Store runtime keys and credentials only in an owner-only temporary manifest; never put them in URLs or commands printed to the evidence log.

The owner registry uses two sources, gateway and authentication, with a lab-specific shared request namespace. Bound each case to at most one hour and 1,000 records and enforce all existing byte limits. Export complete recorded intervals using file positions plus timestamps. Reject an oversized interval rather than silently dropping records. Disclose which endpoints the auth hook covers.

### Compare separate observations

The driver observes actual browser login state and cart behavior, then reads the separately emitted source logs and saved assessment. It must not create the expected source logs itself. Inspect the running DOM before choosing locators. Use Agent Browser for interactive discovery; reuse the installed Playwright stack for repeatable assertions and screenshots. No browser storage-state export, HAR or trace containing authentication tokens.

Run these cases with fresh browser contexts and a lab-created non-MFA account:

| Case | Browser action | Required assessment behavior |
| --- | --- | --- |
| Normal customer | Register, log in, browse, add an item to the cart | One explicit auth success for the measured login; gateway/auth request IDs link; cart activity does not become a purchase/payment claim |
| Wrong password | One incorrect password for that account | One actual auth failure; no successful-login or compromise claim |
| Retry | Two incorrect passwords followed by the correct one | Two failures and one success; stable account pseudonym; any retry explanation remains a possibility |
| Guest browsing | Browse/catalog and use the guest cart without logging in | Real HTTP activity, zero auth events; no invented authentication success |
| Missing auth export | Reimport the normal customer's real gateway window with an explicitly empty auth source | HTTP success remains an HTTP fact; authentication is unknown; label this as deliberate evidence omission |

Provisioning/registration is outside the measured login window. Also send one benign caller-chosen X-Request-ID during a lab request and verify nginx replaces it before the app logs it. Never probe the public Juice Shop demo or exercise exploit challenges.

Pass/fail assertions include:

```python
assert observed_login_state == 'authenticated'  # successful browser flow only
assert auth_outcomes == expected_outcomes       # parsed from the app's independent log
assert all(event['request_id'] in gateway_ids for event in auth_events)
assert assessment['method'] == 'deterministic'
assert assessment['coverage']['reviewed_records'] == saved_unique_records
assert investigation_row_count == 0
assert investigation_event_row_count == 0
```

Open citations in Log Guardian, check every displayed claim against its cited record, and record display omissions rather than treating the 12-fact limit as full presentation. Verify the missing-auth case has zero supplied auth results even though its underlying browser login succeeded. Check a mobile viewport and an authenticated history reload.

## Reuse

- `examples/security-review/nginx.conf` and `sources.json`: existing safe route mapping, gateway-owned request IDs and owner source registry.
- `services/ingestion-service/app/security_adapters.py`: unchanged strict `nginx_json` and `application_auth_json` adapters. No parallel parser in the driver.
- `services/ingestion-service/app/routes/security_cases.py`: existing import, history and read-only assessment endpoints.
- `services/ingestion-service/app/security_assessment.py::build_security_baseline`: unchanged derivation and display policy, exercised through HTTP rather than reimplemented by the test.
- `tests/e2e/test_security_review_ui.py::security_stack` and `upload_example`: reuse the startup/environment and browser upload patterns with real exported files, a new database and no worker.
- The shared `/Users/hitesh/log-guardian/.venv` and its installed browser-testing dependencies. No new Log Guardian dependency or CI matrix entry for this temporary experiment.

## Verification

Capture a clean upstream baseline before instrumentation and compare it with the instrumented shop. Run recorder tests, the affected authentication tests, server typecheck/lint and `npm run rsn` in the isolated build environment. Preserve failures rather than changing upstream challenge caches to obtain a pass.

For Log Guardian, run `make test`, `make test-demo` and `make lint` from the isolated worktree with provider/telemetry variables empty. Run the existing security-review browser suite from `tests/`, then execute `/tmp/lg-juice-business/run.py` against the real running applications. The five-case matrix and assertions above are the live-test acceptance criteria. Authentication test responses may contain tokens in memory; capture only sanitized observations, never full response bodies.

A successful result requires both the browser actions and source-to-assessment checks to pass. A working recorder alone, a successful import alone or a green typecheck is insufficient. Scan and hash the archived artifacts after copying them, verify saved counts from the database independently, and report any unexecuted upstream checks or blocked network dependencies.

## Execution checklist

- [x] Inspect prerequisites and clone the pinned source without installing or executing it.
- [x] Obtain plan approval. Create an issue-linked isolated Log Guardian worktree from the pinned merged revision and a local lab branch in the external clone. Preserve all other worktrees, servers, archives and root-main notes.
- [x] Read the full source files to be changed and upstream test/RSN guidance. Read the existing Log Guardian browser fixture before reusing its startup/import behavior. The first 200 lines of the shop's default config were inspected; do not edit that file without reading the remainder.
- [x] Write and run failing recorder tests, implement the opt-in hook, and verify disabled mode and unchanged login behavior. Test success/failure/unavailable, invalid identities/IDs, pseudonym stability and write failure. Run upstream applicable tests, typecheck/lint and RSN in an isolated build environment. Record any blocker; do not claim upstream validation from compilation alone.
- [x] Build the shop in the background with logs. Preserve source/patch/image identifiers. Start the private shop/gateway and isolated no-model Log Guardian instances. Verify readiness with bounded timeouts, exposed bindings, absence of a direct shop port, no external runtime egress and the real rendered pages before driving scenarios.
- [x] Execute the five cases and request-ID replacement check. Preserve all failures. Import through the real API and exercise the Log Guardian browser, citations and history. No mocked application responses or synthetic auth records.
- [x] Check source-record counts, exact-ID links, claims, unknowns, no Investigation/event writes, local credential scans and desktop/mobile evidence. If a product defect appears, stop and reproduce it before proposing a separately scoped fix.
- [x] Preserve a sanitized experiment archive with runnable scripts, hashes, original source logs, expected-versus-observed results and limitations. Do not archive the shop database, credentials, tokens, HMAC key or raw browser authentication responses. Verify the archive from disk.
- [x] Report actual URLs, cases, checks and failures. Leave only task-owned local services needed for owner inspection, with recorded cleanup commands. Do not stop existing viewers or remove anything outside task-owned resources. No commits, pushes or merges without a new explicit request.

## Initial execution notes

- Execution worktree: `/Users/hitesh/log-guardian-worktrees/48-juice-business`, branch `feat/48-juice-business`, pinned to `d150fac`. External clone is on local branch `lab/log-guardian-business` at the approved `5658473` source.
- Recorder unit tests were written at `~/juice-shop/test/server/securityAudit.unit.test.ts`; a real-API assertion script is at `/tmp/lg-juice-business/securityAudit.api.test.ts`. Neither has run yet because the baseline build has not completed. No hook implementation or login-route edit exists.
- The first baseline attempt used `npm ci`, which failed because the release does not contain a root lockfile. This was a lab setup error, not a product failure. `/tmp/lg-juice-business/baseline-build.log` preserves it.
- The second attempt used upstream's documented `npm install`. Angular generated the application bundles, but the subsequent SBOM command failed with `Error: Missing metafile: dist/frontend/stats.json`. `/tmp/lg-juice-business/baseline-build-install.log` preserves the failure. The production Angular configuration requests `statsJson: true`; the frontend SBOM script expects that exact file. Why the resolved build tool omitted it is not established yet.
- Baseline verification did not run: `/tmp/lg-juice-business/baseline-checks.log` records `BASELINE_VERIFY_BLOCKED=build_failed`. Do not count either setup failure as the recorder's intended red test.
- Node builder image resolved to `node:24@sha256:64af3819f9275802414d7cdc38c27e9d82bd564dec4d4da87d008255d36c63b4`. No host dependency install, app server, provider call, commit or push occurred.
- Execution paused for owner direction. The owner subsequently authorized investigating and fixing the lab build without changing the approved release or bypassing its checks.

## Execution results

- Resolved Angular 22.2.0 writes `browser-stats.json`; the release's SBOM command expected `stats.json`. The lab build changes only that command's input path and keeps SBOM generation enabled. The resulting CycloneDX BOM has 672 components.
- The opt-in recorder's seven unit tests and real-API integration check passed after their recorded red runs. Typecheck, lint and RSN passed. The full upstream API suite has the same 21 failures before/after instrumentation, including network-isolated internet checks. Do not report the full upstream suite as passing.
- Five final scenarios passed with 182 records across reviews and 154 unique source records. The missing-auth review deliberately reuses 28 gateway records. A separate caller-controlled request-ID check passed.
- The database has six cases and 183 stored source records: five final cases plus one retained partial-run case. Investigation and InvestigationEvent counts are both zero.
- Four earlier driver attempts are preserved. They exposed Socket.IO network-idle waiting, an upstream dropdown-label pointer overlap, an incorrect cart-status expectation and an ambiguous Login locator. No Log Guardian product change was needed.
- A later browser probe recorded a Socket.IO handshake 400 through the minimal gateway and one console error. REST business flows and Log Guardian reviews still completed. WebSocket integration remains a limitation; no JavaScript page errors were observed.
- Evidence and runnable checks are in `/Users/hitesh/log-guardian-worktrees/48-juice-business/docs/verification/juice-shop-business/`. Runtime credentials and databases remain outside Git under the owner-only `/tmp/lg-juice-business/` directory.

## Not included

No real business/customer data, production deployment, real payments, attack campaigns, automated remediation, paid model calls, model-quality claims, fine-tuning, continuous collection, load testing, full MFA/OAuth coverage or new order/payment audit schema. Cart state is a browser observation, not a capability claim for Log Guardian. A patched security-training shop is more realistic than authored JSON, but it is not evidence of usefulness on an independent production business.
