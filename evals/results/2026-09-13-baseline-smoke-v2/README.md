# Second live baseline smoke evaluation

The correction candidate did not fix abstention on the selected development case. Both A and B again asserted an unsupported collector-to-request causal link. Step 6 remains incomplete: no inconclusive baseline report was produced.

Four real requests ran on 2026-09-13, one A/B pair for dev-01 and one for dev-06. Model, evidence, temperature, and per-run limits match the first batch. The shared prompt and lexical retrieval changed together. This is a development comparison after inspecting failures, not an independent benchmark or an isolated test of either change.

| Case | System | Expected | Reported | Core diagnosis review | Input/output tokens | Seconds | Estimated USD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dev-01 | A | supported | supported | Deadline mechanism matches | 1044 / 328 | 3.593 | 0.00094240 |
| dev-01 | B | supported | supported | Deadline mechanism matches | 1541 / 337 | 3.624 | 0.00115560 |
| dev-06 | A | inconclusive | supported | Unsupported collector-to-request link | 924 / 271 | 3.619 | 0.00080320 |
| dev-06 | B | inconclusive | supported | Unsupported collector-to-request link | 1581 / 299 | 4.346 | 0.00111080 |

Estimated batch cost: **$0.00401200**, from known returned usage. Across both batches: eight requests, estimated **$0.00768160**. Both four-request authorizations are exhausted; unused dollar allowance does not authorize more requests. There were no retries or ambiguous-usage failures.

## What changed and what did not

B/dev-06 now received `runbook:timeouts`, instead of the first batch's unrelated top-three sections. B/dev-01 received no runbook matches. Removing common-word matches improved the targeted timeout retrieval but did not demonstrate generally better retrieval or diagnosis.

The revised prompt explicitly distinguished missing telemetry from an application failure and required evidence for request-path dependencies. Nevertheless, both dev-06 causes treat missing log export as a reason for gateway timeouts. The evidence establishes timeouts and unavailable search-side telemetry, not a request dependency on the collector. These remain semantic failures even though all cited IDs exist.

Both dev-01 reports retain the supported deadline mechanism. Some observation-level attribution remains incomplete: A cites the handler-completion record for a comparison against the deadline, and B cites acceptance/query/completion records for a deadline comparison without citing the deadline record in that observation. The deadline is available elsewhere in each report. The likely-cause citations do include it. Do not call every claim fully grounded.

Correct abstentions remain **0 of 2** in this batch, versus **0 of 2** in the first. No aggregate supported-claim precision or production accuracy is asserted. Review was by the coding assistant against existing development evidence and rubric, not an independent or blind reviewer.

## Provenance

- Clean revision: `0a97c3f00acdfefe48329f1d0d89a60b3533b59f`.
- Model requested and returned: `gpt-4.1-mini-2025-04-14`; SDK 2.11.0; temperature 0.
- Prompt/schema hash: `7490913eb179976232ddc28f8cbe8e60eb262f7a847fda46cf972fb27131f2cb`.
- Authored development corpus 1.0.0. No held-out case or evaluator label was supplied to the runner.
- Every report contains evidence snapshots, case/corpus/implementation hashes, usage, timings, and limits. `summary.json` records artifact SHA-256 hashes and the offline outcome comparison.
- All four original JSON files are preserved byte-for-byte. Their `completed` status means runner execution succeeded, not that the diagnosis passed review.
- Before requests: 184 tests and lint passed. After requests: schemas, citation membership, byte/output/time bounds, and per-run/total estimated costs were checked offline.

The [first batch](../2026-09-13-baseline-smoke/README.md) remains unchanged. Do not overwrite failures, relabel them as inconclusive, or keep adding prompt instructions without a new diagnosis of the failure. PR #16 remains draft. Further model experiments require fresh authorization.
