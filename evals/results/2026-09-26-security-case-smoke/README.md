# Live security-case smoke: one accepted report, three rejected

This one-shot allowance is closed. Do not rerun this batch or reuse its unused budget.
Four synthetic cases reached the real gpt-4.1-mini-2025-04-14 endpoint. This is not an
independent security-detection benchmark or a faithful native-wire comparison: the
capture adapter reordered JSON-schema properties before sending, as described below.

## Results

| Case | Supplied evidence | Worker result | Estimated USD |
| --- | --- | --- | --- |
| smoke-01 | Six auth failures, four accounts, three addresses, six exact links | Rejected: invalid_report | 0.00289280 |
| smoke-02 | Two failures then one success, one account/address, three links | Rejected: invalid_report | 0.00198080 |
| smoke-03 | Three gateway HTTP 200s, no supplied auth records, no links | Accepted, inconclusive | 0.00166320 |
| smoke-04 | Two failures then one success, one account, three addresses/links | Rejected: invalid_report | 0.00205600 |

- Four provider requests, each HTTP 200 and finish_reason=stop; no retries or follow-up tool calls.
- All 27 supplied records were delivered in the four initial tool reads. Every returned citation ID was a delivered ID.
- 9,950 input tokens, 2,883 output tokens, zero cached input tokens reported.
- Estimated total and uncached upper estimate: USD 0.0085928. This is not a billing receipt.
- Conservative pre-send reservations: USD 0.03163320, within USD 0.025 per case and USD 0.10 total.
- Usage is known for every request. Four committed tool-request/completion pairs and four final status events are preserved.

The driver exited zero because the transport batch finished. It does not mean four
valid reports. All failures remain in the denominator. No additional calls followed.

## What failed

The three rejected responses contain observations and known citations, but choose
outcome=supported with likely_cause=null. Revalidating the preserved responses against
the frozen InvestigationReport produces:

```text
Value error, Supported reports require observations and a cited cause
```

This is a cross-field report-contract failure, not malformed JSON, unknown citations,
missing evidence delivery, a provider timeout or token truncation. The worker correctly
refused to expose these as accepted reports. Their original model content remains in
request-001/002/004.response.json. No outcome was silently rewritten.

The accepted missing-auth report leaves authentication status unknown and does not
infer login success from HTTP 200. Its phrase "No authentication results were recorded
or available" still deserves a scope caveat: the evidence establishes no supplied auth
records, not complete knowledge of what an application recorded elsewhere.

The rejected responses mostly describe the supplied counts, but some suggestions are
poorly scoped. smoke-01 requests transport/handler timing despite no latency symptom.
Requests to inspect payloads or headers need privacy-safe scoping and must not become
permission to collect passwords or tokens. These are assistant observations, not an
independent semantic grade. No suggested action was executed.

## Capture-adapter limitation

The application, frontend and migration files match production revision
3841bf9548b2b76f906cbaa61d34378417a70bbc. The runner additions were committed as 5d5d0c4;
the preparation digest is 72e9c42a42921adbe9cb261d0e6d4efd34b814e57ea0f211a6cbd3a991f28fda.

However, the reused RecordingTransport adds the default billing tier and serializes the
request with sort_keys=True. That changes the report schema's property order:

```text
Native: observations, missing_evidence, alternatives, likely_cause, outcome, suggested_checks
Sent:   alternatives, likely_cause, missing_evidence, observations, outcome, suggested_checks
```

The recorded request hashes reproduce from those sorted bodies. Returned model content
also follows the sorted ordering. The source's comment explicitly intends observations
before the conclusion. This adapter therefore changed a relevant wire property even
though production source bytes were frozen. The failure rate cannot be attributed to
native production ordering from this batch, and changing order is not yet proven to
fix the rejected outcomes.

Context7 returned no snippet for the ordering follow-up; key-order-docs.txt preserves
that lookup result. The previously pinned official guide in
../report-verifier-mock-transport/structured-output-excerpt.txt, lines 1386-1389, states
that Structured Outputs follow schema key order. Original source:
https://developers.openai.com/api/docs/guides/structured-outputs

Next: make capture preserve the native schema order, add an offline wire-equivalence
regression, and obtain a new explicit batch authorization before retesting. Do not relax
the report validator or repair archived responses to turn these failures into passes.

## Execution and preservation

Authorization: docs/plans/security-live-smoke-authorization.md in the repository.
The exact preparation, source/input hashes and dependency versions are in manifest.json
and candidate/. Evaluator-only notes were committed before execution in
evals/security-live-smoke/review-notes.json, but were not loaded by the runner or sent.

The actual FastAPI import and promotion routes ran through ASGITransport against a new
SQLite database per case. The existing worker's run_once claimed and executed its sole
queued run. This exercised real component code and a real provider, not separate API
and worker OS processes during execution. No continuous provider worker was started.
The harness checked that import creates no investigation, a review key cannot promote,
and reopening after execution returns the same run instead of paying twice.

The shared ledger is /Users/hitesh/log-guardian/.git/security-case-smoke-2026-09-26-01.
All 61 original files are preserved. JSON/source files were copied byte-for-byte;
SQLite files are gzip-compressed with decoded bytes verified against the originals.
original-files.json records the original SHA-256 values. Provider captures contain
parsed response JSON and unchanged model-content strings, not a claim of verbatim
HTTP headers or response framing. Credentials and HTTP headers are not archived.
Run the stdlib-only replay check without a key or network:

```bash
python evals/results/2026-09-26-security-case-smoke/verify.py.txt
```

The launch used OTEL_CONSOLE=0. In this frozen implementation any nonempty value enables
tracing, so console spans were emitted. No collector endpoint was configured. The raw
console log stays private outside the repository; use an unset or empty variable for
future disabled-tracing runs. No production code was changed to hide this behavior.

Preparation checks passed 762 offline tests, six demo tests and lint. The new four
runner checks cover real route/worker rehearsal, reservation before the mock provider,
request/cost limits, stopping on provider failure and refusing ledger reuse. This did
not catch the schema-order change, which is an explicit test gap.

## Browser inspection

A read-only local server uses copies of the four databases, with provider credentials
unset and no worker. All write methods return 405. It serves the unchanged security UI:

http://127.0.0.1:8484/

The landing page links smoke-01.localhost through smoke-04.localhost on port 8484.
Use Chromium for those names; the plain loopback UI defaults to smoke-03. Keys remain
in the owner-only /tmp/lg48-live-viewer-runtime.json file, not in this archive.
Portless had no running proxy; the pinned loopback fallback avoided privileged proxy
or certificate changes.

The browser checks exercised all four saved cases, opened the accepted report's
citation, confirmed failed reports stay empty, checked write refusal and empty browser
storage, and observed no page errors. ui-verification.txt and ui-smoke-*.png preserve
that inspection. The helper scripts are included as text for provenance, not production
features. Viewing these results sends no new model requests.

There is no customer traffic, attack execution, production deployment, independent
review, attribution to AI actors or new spending authorization in this archive.
