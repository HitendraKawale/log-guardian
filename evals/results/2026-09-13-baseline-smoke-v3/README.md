# Third live baseline smoke evaluation

A now abstains on dev-06 without inventing a request dependency on the collector. B also emits an inconclusive label, but repeats that unsupported dependency in alternatives and checks. Count **two abstention labels, one core abstention review pass**. Do not count B's label alone as a semantic success.

Step 6's representative live reports are [B/dev-01](dev-01-B.json), which identifies the supported deadline mechanism, and [A/dev-06](dev-06-A.json), which declines to assert a cause and requests missing search-side evidence. These are real provider responses with provenance, not scripted examples. Claim-level limitations remain below.

| Case | System | Reported | Core review | Input/output tokens | Seconds | Estimated USD |
| --- | --- | --- | --- | --- | --- | --- |
| dev-01 | A | supported | Deadline mechanism matches | 1044 / 329 | 3.932 | 0.00094400 |
| dev-01 | B | supported | Deadline mechanism matches | 1541 / 319 | 4.167 | 0.00112680 |
| dev-06 | A | inconclusive | Core abstention passes | 924 / 267 | 3.285 | 0.00079680 |
| dev-06 | B | inconclusive | Unsupported dependency remains in alternatives | 1581 / 370 | 3.126 | 0.00122440 |

Estimated batch cost: **$0.00409200**. Across all three batches: twelve requests, estimated **$0.01177360**. Every request returned known usage. There were no retries. The four-request allowance is exhausted even though most of the $0.10 dollar allowance remains.

## Comparison and review

The [second batch](../2026-09-13-baseline-smoke-v2/README.md) used outcome-first report ordering and produced zero abstention labels. This batch moved observations and missing evidence before the conclusion. The prompt text, model, SDK pin, questions, corpus, retrieval, field definitions and validators were unchanged. Offline comparison verified identical tool calls/results and input-token counts for each pair; tool execution times differ and are not evidence changes.

A/dev-06 now asks for search-side logs/traces and timing to distinguish transport from handler delay. It does not claim that missing telemetry caused the application timeout. It still over-interprets `last_received_before_window=true`: the evidence establishes unavailable export during the window, not its prose claim about receipt before the window. The pool snapshot is not proof of pool state throughout the interval. These are observation-level limitations, not an asserted root cause.

B/dev-06 moves the previous collector-to-timeout claim into an alternative. Its missing-evidence list and checks also assume gateway-to-collector request traffic that the observations do not establish. This is a semantic failure, despite a null likely cause, an inconclusive label and valid citation IDs. A runbook-only alternative about short deadlines is a generic possibility, not case-specific evidence.

Both dev-01 likely causes cite the deadline and handler/timeout records. The internal source of the handler delay remains unknown. A's deadline-comparison observation still omits the deadline citation, although it appears elsewhere. A's suggestion to consider increasing deadlines is not a verified fix or a read-only check. B's health-probe observation must remain scoped to the probe, not general request health. No suggested action was executed.

The order-only change coincided with better abstention on this selected case. This four-request trial does not establish a causal effect or general reliability; temperature zero is not a guarantee of identical repeated outputs. No hidden reasoning fields, case-specific rules, new model, or evaluator labels were added to runtime inputs. Review was by the coding assistant against existing development evidence and rubric, not an independent or blind reviewer. No held-out evaluation has run.

## Provenance and checks

- Clean revision: `8edf09ed34d896ea54e76fcc9ccc6632c8c1b9f7`.
- Requested and returned model: `gpt-4.1-mini-2025-04-14`; SDK 2.11.0; temperature 0.
- Prompt/schema hash: `cb18775883d13c3740332ed3e98b1b0f7358b4a494967a2e360cafd77e2f66c6`.
- Authored development corpus 1.0.0, not production incidents or a blind benchmark.
- The four original JSON files are copied byte-for-byte. Each includes evidence, case/corpus/implementation hashes, usage, timings, pricing and limits. `summary.json` records SHA-256 hashes and the offline review separately from reported labels.
- Offline checks validated report schemas, citation membership, byte/token/time/cost bounds, clean provenance, and unchanged evidence relative to batch two. These checks do not prove semantic support.
- Previous batches remain unchanged. All errors and semantic failures remain visible rather than being rewritten after a later candidate improves.
