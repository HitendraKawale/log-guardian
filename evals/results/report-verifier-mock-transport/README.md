# Mock verifier transport evidence

No paid request or real provider connection occurred. The driver replaces HTTP with
httpx.MockTransport and forbids real socket creation. It wraps the prior label-shaped
scripted reviews in fake provider envelopes with invented usage values.

```text
mode: mock
paid_requests: 0
attempted: 17
local-invalid controls not sent: 1
fatal: null
usage_complete: true
```

Replay retained all eighteen cases and produced the intended scripted eight passes,
nine semantic rejections and one local block. This proves transport plumbing and
accounting behavior, not model correctness, provider schema acceptance or injection
resistance. The USD 0.2147876 reservation and USD 0.0285600 usage upper estimate are
simulated calculations, not spending or billing receipts.

## Frozen wire mapping

Wire manifest SHA-256:
`405b432e505149b535eabab71a34c325ce1ea1b044f3521ad8d479be7c7c3b85`.

It references the unchanged provider-neutral preparation and hashes each exact wire
request, the adapter, reused durable writer and HTTPX version. The body preserves
messages and the v2 schema verbatim. It adds pinned model, default tier, store=false,
stream=false, temperature=0, max_completion_tokens=4096 and strict json_schema format.
There are no tools or credentials in the wire artifacts.

Each reservation commits before mocked dispatch. Each decoded HTTP witness commits
before parsing, model/tier/usage checks or extracted review persistence. Witnesses
store exact decoded body bytes as base64 with status, hash and completeness, not raw
compressed HTTP frames. Responses over 128 KiB retain a bounded prefix and fail.
Extracted verifier JSON is separately capped at 16 KiB; captures may include one
sentinel byte to demonstrate overflow. A missing completion after a reservation is
unknown, never a reason to replay the attempt.

Transport/accounting failures stop the batch. Later cases remain not_attempted.
Refusals, truncated completions, tool proposals and malformed reviews with known
usage become verifier errors without losing that usage. None triggers a retry,
repair, execution or fallback acceptance. Evidence-write failures abort immediately.
The offline scorer can consume extracted reviews, but does not authenticate the
provider or replace the transport summary's attempted/unattempted distinctions.

## Reproduction

Use new output directories from the repository root:

```bash
.venv/bin/python evals/report_verifier_transport.py --output /tmp/verifier-wire
.venv/bin/python evals/results/report-verifier-mock-transport/driver.py.txt --wire /tmp/verifier-wire --output /tmp/verifier-mock
.venv/bin/python evals/report_verifier_eval.py replay --prepared evals/results/report-verifier-offline-runner-verified/prepared --responses /tmp/verifier-mock/responses --output /tmp/verifier-mock-replay
.venv/bin/python evals/report_verifier_eval.py score --replayed /tmp/verifier-mock-replay --output /tmp/verifier-mock-score
```

The transport CLI only prepares files. The callable rehearsal requires exactly
httpx.MockTransport; no real-transport fallback or live flag exists. This is not an
OS sandbox for arbitrary caller-supplied Python handlers.

## Verification and limits

Twenty-two new transport checks passed. Full verification ran make test, make
test-demo, make lint and git diff --check: 639 offline tests plus six demo tests
passed; Ruff reported all checks passed and 372 files already formatted. Existing
demo warnings remain in verification.txt. Tests cover strict wire preservation,
reservation order, gzip decoding, durable capture before validation, malformed usage,
wrong model/tier, refusals, tool proposals, oversize responses, deadlines, write
failures, no retry, stale bundles and refusal of non-mock transport.

Context7 captures preserve API-format and pricing references. Its schema coverage was
incomplete, so structured-output-excerpt.txt preserves the relevant official guide
sections fetched directly. Documentation is not proof of actual provider acceptance.

The owner approved limits and offline adapter preparation, not a preparation commit
or live sends before the remaining execution checks. No live ledger was claimed.
Credential handling, a clean frozen execution revision and an explicitly gated live
driver still need separate preparation and verification. Production remains unchanged.
