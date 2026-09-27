# Business-log live model test

The live report path is not reliable on these four development cases. One report was
accepted, two violated the supported/cause contract, and one exhausted the output-token
limit. The capture-order correction worked on the actual sent requests, but it did not
make these reports consistently usable. No report was repaired or retried.

The owner approved this new synthetic batch and a local freeze commit. The allowance
security-business-smoke-2026-09-26-02 is now closed. No unused request or cost allowance
may fund another attempt. No push or production deployment was performed.

## Actual results

| Case | Business scenario | Supplied records | Result | Estimated USD |
| --- | --- | ---: | --- | ---: |
| smoke-01 | Six failed logins across four account references, a later 429, catalog/cart traffic | 15 | invalid_report: supported with no cause | 0.00289240 |
| smoke-02 | Two login failures then success for one account/address, catalog/cart traffic | 8 | incomplete_output: stopped at 1024 output tokens | 0.00276720 |
| smoke-03 | Gateway 200/401/503 responses, no supplied auth records | 4 | Accepted, inconclusive | 0.00216080 |
| smoke-04 | Two failures then success, later order/checkout HTTP 200s with unknown business effects | 8 | invalid_report: supported with no cause | 0.00255560 |

All 35 records reached the model through four initial read_security_evidence calls.
None of those pages was truncated. The model made no follow-up tool calls.
All four provider requests returned HTTP 200. Three finished with stop; smoke-02 finished
with length and incomplete JSON. A successful HTTP request is not a successful report.

- Model: gpt-4.1-mini-2025-04-14, standard/default billing tier.
- Four requests out of a maximum 24; no SDK, transport or report retries.
- 11,756 input tokens and 3,546 output tokens; zero cached input tokens reported.
- Estimated usage cost: USD 0.0103760. This is not a billing receipt.
- Conservative reservations: USD 0.03393520, within USD 0.025 per case and USD 0.10 total.
- Every request has captured usage. No unpriced or ambiguous attempt is omitted.

LIVE_EXIT=0 meant the batch completed, not that all reports passed. Three failed reports
remain in the denominator and their raw responses remain available.

## What the model said

The complete responses in smoke-01 and smoke-04 describe observed counts and request
pairs, then return likely_cause=null and outcome=supported. Revalidation against the
unchanged application schema yields:

```text
Value error, Supported reports require observations and a cited cause
```

The worker rejected both, rather than publishing a contradictory verdict. Their citation
IDs were all delivered IDs. Membership does not establish that each citation supports
every part of its associated claim. For example, smoke-04 names customer-3091 while
citing only the summary, which contains an account count but no account reference.
The account appears in delivered event records, but those are not cited for that claim.

For smoke-02, the model used most of its output on six observations and repeated long
citation identifiers. The preserved text ends inside the likely_cause field name. Its
cause and verdict cannot be inferred from that fragment. The worker rejected it as
incomplete_output; no JSON completion or continuation request was attempted.

The accepted smoke-03 report kept authentication outcomes unknown despite HTTP 200s.
It named the missing authentication records and correlation data. Its suggestion to
investigate why no auth results were "recorded" needs a scope caveat: this fixture only
establishes absence from supplied records, not that the real service recorded nothing.

Other review cautions:

- Unlinked catalog/cart requests do not by themselves imply unauthorized access or a
  telemetry defect. Authentication is not necessarily expected on every route.
- A successful login and later HTTP 200s do not prove the same session, account takeover,
  order creation, payment completion or data access. No such business-state evidence was supplied.
- Suggestions to inspect payloads or headers require privacy-safe scoping. They do not
  authorize collecting passwords, cookies or tokens.

These are the fixture author's observations, not independent semantic adjudication.
The scenarios and expectations were recorded before execution in
evals/business-model-smoke/review-notes.md and were not loaded by the runner.

## Corrected capture, frozen application

The local freeze commit is d41bffe. Application, frontend and migration files still match
3841bf9548b2b76f906cbaa61d34378417a70bbc. No prompt, report validator, model, output ceiling
or retry setting changed for this batch.

Preparation SHA-256:
4625a78f748a3c945eab1d1c239582b0051c27176960a1d5ede644a4cdce9d21

Every reservation contains request_json, the exact UTF-8 body sent, and its SHA-256.
Its report schema retains the native order:

```text
observations, missing_evidence, alternatives, likely_cause, outcome, suggested_checks
```

The separately parsed request object is canonically serialized for convenient inspection;
use request_json when inspecting wire order. The archive verifier reconstructs the sent
bytes, checks the hash and compares schema order with the frozen source declaration.

The corpus changed from the previous four-case smoke. Comparing acceptance counts cannot
isolate a causal effect of changing wire order. The present counterexamples do show that
correct ordering alone is not sufficient for reliable reporting on these inputs.

## Execution and evidence

This was a live model run on authored business-shaped logs, not traffic from a real
business and not an attack against a live login system. Addresses use documentation
ranges and account references are synthetic. No passwords, tokens or customer data were
submitted. The logs match the prescribed nginx/application-auth import formats.

The actual FastAPI import/promotion routes ran through ASGITransport. The actual worker's
run_once claimed the sole queued run in each isolated SQLite database. This did not test
separate API/worker processes, production concurrency, collection completeness, traffic
capacity or live pagination. No continuous provider worker was started. Tracing was
disabled with empty opt-in variables.

Offline preflight passed 762 tests, six demo tests and lint. The rehearsal delivered
15/8/4/8 records without truncation and verified ordered capture. Those mock reports were
not evidence of model quality; the live results above are reported separately.

The original 61 ledger files are preserved. JSON/source files are copied byte-for-byte;
SQLite files are compressed with decoded hashes checked against the originals.
original-files.json holds those original hashes. manifest.json and candidate/ preserve
the execution freeze. analysis.json records the offline inspection of returned content.
Raw model text, including the truncated response, remains unchanged in response captures.
Provider headers and credentials are not archived. No independent reviewer was used.

Run without a key or network:

```bash
python evals/results/2026-09-26-business-model-smoke/verify.py.txt
```

## Read-only product view

The unchanged security UI can inspect copied databases at:

http://127.0.0.1:8485/

This is a separate view from the previous batch on port 8484. It runs
/tmp/lg48-business-viewer.py on pinned loopback port 8485, without a model credential or
worker. Portless remained unavailable without privileged proxy setup, so no shared proxy
was changed. Owner-only review/execution keys are in
/tmp/lg48-business-viewer-runtime.json. The landing page links all four cases using
.localhost names supported by Chromium; the plain loopback UI defaults to smoke-03.

Browser checks opened all four actual results, verified the two validation failures and
one truncated-report failure stayed empty, followed an accepted report citation to its
HTTP-status evidence, and confirmed POST refusal with 405, empty browser storage and no
page errors. ui-verification.txt, ui-smoke-*.png and the copied helper scripts preserve
this inspection. All database files used by the view are disposable copies; original
ledger and archived evidence remain unchanged. Viewing them cannot queue new execution.

The next work is offline report-contract and verbosity testing. Do not weaken validation,
silently increase token limits, revise these results or start another model batch without
new authorization. No product-readiness or security-accuracy claim follows from this run.
