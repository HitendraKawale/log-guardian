# Security-case live smoke authorization

The owner approved this exact proposal in chat with "yes": four synthetic cases,
gpt-4.1-mini-2025-04-14, no automatic retries, at most 24 provider requests,
USD 0.025 estimated allowance per case and USD 0.10 total. This is a one-shot
smoke test, not an independent attack-detection benchmark. No customer data is allowed.

The production candidate is 3841bf9548b2b76f906cbaa61d34378417a70bbc. Application,
frontend and migration bytes must remain unchanged. Runner/authorization additions
are separate from the production candidate and get their own frozen hashes before send.

Cases are authored development data: suspicious failures, ordinary retries, absent
authentication evidence and successful authentication with unknown downstream impact.
Neutral case IDs and runtime records go to the product. Evaluator notes do not.

## Execution checklist

- [ ] Freeze source, input, runner and dependency hashes; verify the production revision.
- [ ] Rehearse real import/promotion/worker code with an exact httpx.MockTransport.
- [ ] Check request/cost caps, durable pre-send reservation, capture-before-dispatch,
  failure stopping and single-use ledger behavior without network calls.
- [ ] Execute the approved batch once, sequentially, with isolated SQLite databases.
- [ ] Preserve all results, failures, usage and receipts; close the allowance.
- [ ] Review actual outputs against delivered evidence and expose results for inspection.

Use a new exclusive ledger under the shared git directory:
security-case-smoke-2026-09-26-01. Never reuse prior evaluation ledgers. An existing
ledger refuses execution, even if interrupted. Unknown usage, provider/transport
failure, capture failure or worker interruption stops the batch. No automatic reruns.

Reuse the existing RecordingTransport in evals/investigator_pilot.py with this batch's
separate configuration. Its conservative UTF-8-byte reservation is committed and fsynced
before sending; reservations are never refunded within the batch. Provider headers and
credentials are not archived. The transport admits only the fixed OpenAI endpoint,
model, default billing tier and 1024 output-token ceiling. SDK and HTTP retries stay off.

Current pricing was retrieved through Context7 from the official model page:
https://developers.openai.com/api/docs/models/gpt-4.1-mini
USD 0.40 input, USD 0.10 cached input and USD 1.60 output per million tokens.
Reservations charge input at the uncached rate. Estimates are not a billing guarantee.

The HTTP routes will run through ASGITransport against the actual FastAPI application,
not a stub. Each case gets a new database; only its explicitly promoted run is claimed
and executed by the existing worker. No continuously running provider worker is started.
A later local browser may inspect the saved results without running another model.

The evaluator and fixture author are the same assistant, with repository context.
There is no independent labeling, held-out accuracy claim, adversarial robustness claim,
production deployment or automatic blocking authorization. Existing closed allowances
remain closed. The approved spend does not authorize additional model calls after this batch.
