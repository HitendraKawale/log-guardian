# Typed business-log live authorization

The owner answered "yes" to the explicit proposal for four fresh synthetic production-
shaped cases, gpt-4.1-mini-2025-04-14, at most 24 requests and USD 0.10 estimated total,
no retries, a new ledger and locally committed freeze. No actual production logs,
customer data, production access, push or deployment are authorized.

The exclusive one-shot ledger is security-typed-business-2026-09-27-04 in the shared git
directory. All earlier allowances remain closed. Existing-ledger refusal applies even
if execution is interrupted. Unused requests or reservation balances cannot fund a rerun.

## Frozen scope

Application baseline: 08fde8fd46c2e2da3fab284fce4e818ee87839c5. No application or frontend
changes accompany this batch. Only runner pins, synthetic inputs and preparation records
change. The model selects evidence IDs and fixed codes; the host generates v2 facts,
hypotheses, unknowns and checks. Store model selections separately from host-rendered
reports when reviewing results. Inconclusive is host-owned, not a model diagnosis.

Inputs: evals/typed-business-live/inputs.json, smoke-01 through smoke-04, 41 synthetic
records in total: failed-login burst, retries then success, missing auth records, and
post-login business requests with unestablished effects. Addresses are documentation
ranges. Account references, requests, dates and business routes are invented. No
passwords, cookies, tokens, request bodies or real customer identities are included.

Use the existing owner source registry in examples/security-review/sources.json and the
same bounded API/worker path. Author expectations remain outside model inputs. These
are development fixtures authored and reviewed by the implementing assistant, not an
independent held-out benchmark or samples of actual production traffic.

## Execution boundary

Before any request, commit a clean local freeze and verify manifest hashes, application
bytes against the baseline, an unused ledger and the mock rehearsal. Freeze details
live in evals/typed-business-live/freeze.json. Rehearse actual import/promotion routes,
run_once, evidence delivery, v2 assembly and native schema-order capture without a key.

Use four isolated SQLite databases, one run per case, no continuous worker. The fixed
endpoint is https://api.openai.com/v1/chat/completions with default billing tier.
Limits: six requests and USD 0.025 conservative reservations per case, 24 requests and
USD 0.10 reservations total, 1024 output tokens per request. Existing tool/evidence/time
limits remain. SDK and HTTP retries are disabled. There is no automatic repair or retry
of a rejected selection or truncated output.

Reserve and fsync before dispatch. Preserve exact sent JSON and hash, then capture the
response before the worker consumes it. Stop on ambiguous usage, provider/transport/
capture failure or worker interruption. Known-usage invalid reports remain failures;
remaining authorized cases may continue. Close the allowance after this single attempt.

Pricing uses the preserved reference in evals/security-live-smoke/pricing.txt: USD 0.40
input, USD 0.10 cached input, USD 1.60 output per million tokens. Reservations assume
uncached input. Estimates are not provider billing guarantees or receipts.

## Review

Preserve all raw selections, rejections, usage, receipts, generated reports and input
hashes. Check useful evidence selection and applicability of checks separately from
schema acceptance and deterministic rendering. Do not claim the host's fixed wording
proves that the model diagnosed correctly. Compare descriptively with earlier batches;
changed inputs and contract prevent a controlled before/after accuracy claim.

No further paid calls, automated remediation, independent-accuracy claim, production
capacity claim, push, merge or deployment follows from this authorization.
