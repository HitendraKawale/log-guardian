# Verifier transport preparation

The owner approved the proposed model/request/spending limits and offline adapter
preparation in chat. This does not approve a preparation commit, claim a live ledger,
or waive the clean-revision and execution checks. Live calls remain blocked.
The earlier batch proposal records the proposal as it stood before this approval.

Approved ceilings: gpt-4.1-mini-2025-04-14, seventeen requests, one per eligible report,
zero retries, USD 0.10/report and USD 2 total. Carry forward the proposal's stricter
4096-output-token, 60-second/request, twenty-minute/batch and 128-KiB wire limits.
The original eighteen cases remain in the denominator, including local-invalid v13.

## Implementation plan

```text
[frozen preparation] -> [exact provider requests] -> [mock HTTP only]
                                                        |
[offline scorer] <- [review JSON + durable accounting witnesses]
```

| File | Decision |
| --- | --- |
| evals/report_verifier_transport.py | Map exact schema/messages to Chat Completions; rehearse reservation, bounded capture, deadline and response checks using mandatory MockTransport |
| evals/tests/test_report_verifier_transport.py | Fail-first tests for mapping, reservation order, usage/model validation, errors, deadlines and no real transport |
| docs/plans/report-verifier-transport.md | Record approval scope, documentation evidence, verification and remaining live gates |

- [x] Write failing transport tests.
- [x] Preserve messages and schema unchanged. Set pinned model, default tier, store=false, temperature=0, stream=false and max_completion_tokens=4096. Omit tools entirely.
- [x] Reuse existing durable JSON writer; add raw-byte capture only where JSON reserialization would lose evidence.
- [x] Reserve before each mocked dispatch, capture before parsing, retain failed reservations, stop on ambiguous transport/usage failures and keep later cases unattempted.
- [x] Enforce request/response caps, strict usage and model/tier binding, complete non-tool completions and host review checks. Account for known usage even when the review fails.
- [x] Require exactly httpx.MockTransport. No key read, real transport constructor, live flag or shared-ledger creation.
- [x] Run the full affected suites and a seventeen-request mock rehearsal. Preserve wire hashes and witnesses separately from all previous archives.

Evidence: evals/results/report-verifier-mock-transport/. All seventeen mocked requests
completed with known simulated usage; v13 was never sent. Replay and scoring retained
eighteen cases. No real sockets or model calls were allowed. The full suites passed
639 offline tests plus six demo tests, with lint clean. Twenty-two tests cover this
adapter. Wire manifest: 405b432e505149b535eabab71a34c325ce1ea1b044f3521ad8d479be7c7c3b85.

## Documentation

Context7 retrieved official Chat Completions request-format documentation and pricing
at https://developers.openai.com/api/docs/models/gpt-4.1-mini. The retrieved price is
USD 0.40 input, USD 0.10 cached input and USD 1.60 output per million tokens. Reserve
at noncached rates. These estimates are not billing receipts.

Context7 did not cover the full schema subset, so the official structured-outputs
guide was retrieved directly at https://developers.openai.com/api/docs/guides/structured-outputs.
It documents nested anyOf, references, number bounds and minItems/maxItems, requires
closed objects and required fields, and disallows allOf/if/then/else. The v2 schema
uses nested anyOf rather than those unsupported composition keywords. Keep the exact
schema; do not weaken it to make provider errors disappear.

Documentation and mocked requests do not prove the provider accepts this exact
snapshot/schema combination. Any real provider rejection will consume that attempt,
remain in the results and never trigger a silent schema change or retry.

## Remaining live gates

No live execution implementation is enabled in this change. A future live driver
must enforce the approved exclusive shared ledger, a frozen transport revision and
a clean committed tree. A preparation commit still needs explicit permission.
Provider credentials must be supplied only at that later boundary, never archived;
credential-echo handling is not exercised by this key-free mock adapter.
No original allowance or artifact may be reused or overwritten.
