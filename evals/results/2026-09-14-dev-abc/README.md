# A/B/C development comparison

C, the adaptive loop, performed worst on this development set: 4 of 8 core review passes versus 7 for A and 7 for B. Adaptive retrieval did not beat fixed retrieval here, as the plan anticipated it might not. Do not present C as the headline system on these numbers.

24 runs on clean `ad7f95f0ba86b2a9e0182680dccfb9c1161e51ef`, 46 provider requests, estimated **$0.03470640** total, all usage known, no retries. Authorization allowed 64 requests and $0.60; the 24-run allocation is exhausted. Review is by the coding assistant against `labels.jsonl`, not independent or blind. Eight authored cases cannot establish general reliability.

| System | Completed | Failed | Core review pass | Cost (USD) |
| --- | ---: | ---: | ---: | ---: |
| A (one log query) | 7 | 1 | 7/8 | 0.00743520 |
| B (fixed log+summary+runbooks) | 8 | 0 | 7/8 | 0.01112600 |
| C (adaptive tool selection) | 6 | 2 | 4/8 | 0.01614520 |

Per-run outcomes, usage, latency, hashes and review notes are in `summary.json`. Original JSON artifacts are byte-identical copies.

## Failure analysis (before any tuning)

1. **C searches too narrowly.** C's text filters (`database connection`, `ERROR`, `401`, `error`, `timeout`) frequently matched nothing because `text` is a literal substring of the message and does not match the level field. On dev-02 it missed all orders-side evidence and abstained unnecessarily; on dev-03 it burned six requests and hit `model_budget` without a report; on dev-04 it diagnosed the typo without retrieving the configuration/registration records that ground it (correct-sounding but insufficiently grounded, counted as fail).
2. **Report validation failures are opaque.** A/dev-08 and C/dev-05 failed `invalid_report`; rejected raw output is deliberately not archived, so the exact schema/citation defect is unknown. Both count in the denominator.
3. **dev-06 abstention remains split.** A and C abstained correctly; B again asserted the collector export dependency. Same failure family as previous batches.
4. **Non-read-only suggestions persist.** Several reports suggest remediation (increase pool size, fix configuration) despite the prompt limiting suggestions to read-only checks.

Cost/latency: C used 2–6 requests per case (mean 3.75) and cost roughly 2.2x A. B is one request with more input.

## Candidate directions (not yet applied)

- Clarify in the `query_logs` tool description that `text` matches the message only, literally, and that an unfiltered query is cheap and preferred first.
- Consider a first-pass unfiltered query or summary before filtering.
- These change C's guidance only; any change requires a fresh evaluation before quality claims.

Prompt, schema, model and corpus were frozen for the whole batch. No tuning happened before or during these runs.
