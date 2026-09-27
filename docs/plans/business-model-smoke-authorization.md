# Business-log live model authorization

The owner approved a new batch in chat with "yes": four synthetic e-commerce cases,
gpt-4.1-mini-2025-04-14, at most 24 provider requests, no automatic retries,
USD 0.025 estimated allowance per case and USD 0.10 total. The owner also authorized
a local commit freezing the tested code and inputs. No push or deployment is authorized.

This is a new allowance: security-business-smoke-2026-09-26-02. The previous
security-case-smoke-2026-09-26-01 allowance stays closed. Never reuse its ledger.
The new ledger lives in the shared git directory and must be created exclusively.

## Scope

- Suspicious failures across accounts, with ordinary storefront traffic and a 429.
- Ordinary retries followed by successful authentication and storefront requests.
- Gateway requests with no supplied authentication records.
- Authentication success followed by gateway order/checkout requests whose business
  effects are not established by HTTP status alone.

Records are authored development fixtures, not customer logs or generated attacks on a
real business. Source formats match the product's prescribed nginx and application-auth
JSON. Addresses use documentation ranges, account references are synthetic, and payloads,
passwords, cookies, tokens and customer identities are excluded. Reviewer expectations
are separate and never loaded into a provider request. There is no independent accuracy
claim. This changed corpus cannot isolate the causal effect of correcting schema order.

## Frozen execution

Application/frontend/migration bytes remain at 3841bf9548b2b76f906cbaa61d34378417a70bbc.
The capture adapter now preserves schema property order and records exact sent JSON
alongside its SHA-256. Canonical hashes and historical archives remain unchanged.
No prompt or report-validator change is included. New runner/input/dependency hashes
are frozen before execution, separately from the production revision.

Use the actual FastAPI import/promotion routes through ASGITransport and the actual
worker's run_once, with a new SQLite database per case. Do not start a continuous worker.
Each case is attempted once. Imports cannot spend; promotion is explicitly authorized.
Reopening a terminal investigation must return the same run, not a paid retry.

The transport admits only the fixed OpenAI endpoint/model and default billing tier,
with 1024 output tokens and SDK/HTTP retries disabled. Conservative UTF-8-byte-based
reservations are fsynced before sending and never refunded within this batch. Stop on
ambiguous usage, provider/transport/capture failure or worker interruption. Preserve
known-usage invalid reports and continue the remaining approved cases without retries.

Pricing reference: evals/security-live-smoke/pricing.txt and
https://developers.openai.com/api/docs/models/gpt-4.1-mini.
Rates are USD 0.40 input, USD 0.10 cached input and USD 1.60 output per million tokens.
Reservations use uncached input pricing. These estimates are not a billing guarantee.

## Checks

- [ ] Validate inputs and record the fixture author's expectations before execution.
- [ ] Rehearse routes, worker, native wire order, exact capture and limits offline.
- [ ] Commit the tested freeze locally; verify a clean tree and unused new ledger.
- [ ] Execute once, preserve all responses, failures, usage and tool receipts.
- [ ] Close the allowance and review claims separately from structural acceptance.

No customer-data sharing, remediation, independent review, new deployment or additional
paid calls beyond this batch are authorized. The gate waiver for the capture-order fix
and this batch's chat approval do not authorize later spending.
