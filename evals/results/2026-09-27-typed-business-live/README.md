# Typed business-log live batch: two completed, two rejected

Four real model requests processed 41 synthetic, production-shaped business records.
Two selections produced host-generated assessments. Two were rejected as invalid_report.
There were no truncated responses or retries. The allowance is closed.

This is not a 2/4 diagnosis-accuracy score. The model chooses IDs and fixed codes; the
application writes factual text, mandatory unknowns and the inconclusive outcome.

## Results

| Case | Scenario | Records | Result | Input / output tokens | Estimated USD |
| --- | --- | ---: | --- | ---: | ---: |
| smoke-01 | Eight failed logins across four account references, plus catalog/cart and a login 429 | 19 | Completed | 4337 / 155 | 0.0019828 |
| smoke-02 | Same-account failures followed by success, all login HTTP responses 200 | 8 | invalid_report: source-local IDs selected | 2582 / 68 | 0.0011416 |
| smoke-03 | Gateway login responses but no supplied auth records | 6 | Completed | 2257 / 147 | 0.0011380 |
| smoke-04 | Auth failure then success, later order/checkout/status requests | 8 | invalid_report: unsupported hypothesis and source-local IDs | 2578 / 67 | 0.0011384 |

All four requests returned HTTP 200 and finish_reason=stop. Every supplied row reached
the initial read_security_evidence page without truncation. There were no follow-up
tool calls. Usage was known for all requests: 11,754 input tokens, 437 output tokens,
zero cached input tokens. Estimated cost and uncached upper estimate were USD 0.0054008;
conservative reservations totaled USD 0.03280640. These are estimates, not billing receipts.

The driver returned LIVE_EXIT=0 because the authorized attempt ended without a fatal
transport/usage failure. That does not mean all reports succeeded.

## What failed

### The model selected the wrong ID namespace

smoke-02 returned:

```json
{"focus_evidence_ids":["commerce-v2-auth-2-001","commerce-v2-auth-2-002","commerce-v2-auth-2-003"],"hypothesis_codes":["repeated_login_attempts","retry_possible"],"check_codes":["read_auth_results","read_rejection_reasons"]}
```

Those strings exist inside delivered source records, but they are not selectable outer
evidence IDs. The tool exposes both an outer evidence_id such as security-event:<hash>
and an inner content.evidence_id containing the original source-local record ID. This
is an observed interface ambiguity, not proof that the model invented records.
The assembler rejected the selection rather than silently resolving ambiguous aliases.

smoke-04 made the same namespace error for three IDs. It also selected
repeated_login_attempts although the whole-case summary contains exactly one auth
failure and one success. That hypothesis requires more than one recorded failure.
Offline replay raises Unsupported security hypothesis before resolving the bad focus
IDs. Both defects remain in analysis.json; do not reduce this to only a citation failure.

No report was stored for either rejected case. The UI shows failed: invalid_report,
not a repaired assessment. Wrong source-local IDs and source-qualified selectable IDs
remain distinct. No validator was relaxed and no response was repaired.

## What the completed assessments contain

- smoke-01 selects the whole-case summary, an explicit auth-failure record and the login
  HTTP 429. The host reports eight failures and no success, names the cited account and
  keeps mistakes versus unauthorized guessing as possibilities. Rejection-reason review
  is relevant. The extra auth-results check is permitted by unlinked records, but those
  records also include ordinary catalog/cart traffic; this does not prove missing telemetry.
- smoke-03 selects the summary and login HTTP 401/503 records, with read_auth_results as
  its only check. The host explicitly states that authentication outcome is unknown
  because no auth records were supplied. It does not translate HTTP status into an
  authentication outcome or claim an auth-service recording defect.

The prior accepted false "successful login attempt (HTTP 200)" claim did not recur in
the completed missing-auth assessment. That is evidence of this restricted host-rendering
path, not evidence that the model independently learned the distinction. The model did
not select the HTTP 200 records as focus items in that case.

The same assistant authored and reviewed the cases. There was no independent adjudicator.
The checks establish captured behavior, not true actor intent, compromise, business
impact, production capacity or generalized detection accuracy.

## Candidate and preparation

Application candidate: 08fde8fd46c2e2da3fab284fce4e818ee87839c5.
Local execution-freeze commit: e912177.
Manifest SHA-256: d9f98312ad6951ad6e1e2b112992bdcfde5972ea2da8aaa47bfc4176c83701ea.
Ledger: security-typed-business-2026-09-27-04.

The owner authorized four new synthetic cases, gpt-4.1-mini-2025-04-14, at most six
requests/USD 0.025 reservations per case and 24 requests/USD 0.10 total, without retries.
Application/frontend bytes match the pushed candidate. Inputs, authorization and runner
pins were frozen locally; no push or deployment accompanied the experiment.

804 offline tests, six demo tests and lint passed. The mock rehearsal delivered all
19/8/6/8 records, assembled v2 reports and checked exact native wire order/hashes. Its
first attempt intentionally remains in the preparation record: the author accidentally
used a mock response ID equal to the dummy API key, and credential-echo protection stopped
capture. Changing the mock ID fixed the rehearsal. No real request occurred in either
mock rehearsal, and their invented costs do not belong in this live batch's spend.

The cases use strict nginx/auth formats and documentation-range addresses. They contain
no customer data and were not copied from a production system. Actual ASGI routes,
promotion and run_once operated against isolated SQLite databases. Only the provider
was live; this did not test deployed process separation, real login systems or capacity.

Compared with earlier batches, both the contract and input cases changed. Lower output
token usage or different completion counts cannot be treated as controlled estimates of
accuracy improvement. Further execution needs a new authorization. Remaining request
slots and reservations cannot fund a retry.

## Preserved evidence and replay

All 62 original ledger files are preserved. Text/source/JSON files are byte-identical;
SQLite files are gzip-compressed with their decoded hashes checked. original-files.json
records original hashes. candidate/ and manifest.json preserve the frozen source and
inputs. Reservations contain exact request_json and request_sha256. Raw selections are
unchanged in response receipts. analysis.json separates selections, host reports and
replayed rejection reasons. Provider credentials and request headers are not archived.

Run without a key, dependencies or network:

```bash
python evals/results/2026-09-27-typed-business-live/verify.py.txt
```

The verifier checks all source/original hashes, 41 delivered records, exact request bytes,
response usage, the two failures and the missing-auth assessment. The analysis also
replayed the actual assembler against the captured selections with unchanged application
code. SHA256SUMS covers the complete archive, including browser evidence.

## Read-only inspection

http://127.0.0.1:8487/ serves copied databases through the candidate's UI. Chromium opens
the linked smoke-*.localhost case URLs; plain loopback defaults to smoke-03. Keys are in
owner-only /tmp/lg48-typed-business-viewer-runtime.json. They are not in this archive.

The command is the shared venv's Python running /tmp/lg48-typed-business-viewer.py.
Portless is installed, but its shared HTTPS proxy is stopped; the pinned loopback fallback
does not change proxy setup. The viewer has no provider credential or worker, and all
write methods return 405. Older viewers on 8484/8485/8486 were left untouched.

The browser check opened all four statuses, inspected citations in both completed
reports, confirmed empty report panels for failures, checked the missing-auth unknown,
and verified POST 405, empty browser storage and no page errors. ui-smoke-*.png,
ui-verification.txt and the helper scripts preserve those checks.

The next investigation should address selection-interface ambiguity and case-specific
allowed choices, not silently repair these responses or loosen the evidence boundary.
No follow-up code change or additional live call was made during this batch.
