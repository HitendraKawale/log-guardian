# Third baseline evaluation authorization

The user's “continue” approved the immediately preceding request to commit/push the schema-order candidate and make four additional requests on `gpt-4.1-mini-2025-04-14`, with a fresh $0.10 total allowance.

- Revision: `8edf09ed34d896ea54e76fcc9ccc6632c8c1b9f7`, committed/pushed; clean worktree verified.
- Fresh verification: 187 tests passed; lint passed.
- Candidate prompt/schema hash: `cb18775883d13c3740332ed3e98b1b0f7358b4a494967a2e360cafd77e2f66c6`.
- Only report field order changes relative to the second evaluated candidate. Prompt text, model, retrieval, evidence and validators stay fixed.
- Scope: A/B on dev-01 and dev-06, one request each. No retries, held-out cases, or changes within the batch.
- Per invocation: $0.025 conservative allowance. Count failures toward four. Stop on unknown usage/billing or overrun. Unused dollars do not authorize a fifth request.
- Artifact directory: `/tmp/log-guardian-live-baselines-v3.UTrOkl/`.
- Requests consumed: 4 of 4. A/dev-01 $0.00094400 (1044 input, 329 output); B/dev-01 $0.00112680 (1541 input, 319 output); A/dev-06 $0.00079680 (924 input, 267 output); B/dev-06 $0.00122440 (1581 input, 370 output). All completed with known usage; no retries.
- Estimated batch total: $0.00409200. No fifth request is authorized. All three allowances are exhausted: twelve requests, estimated $0.01177360.
- Both dev-06 outcomes are inconclusive, but only A passes core abstention review. B repeats the unsupported collector request dependency in alternatives and checks. Observation-level limitations remain in A and are documented.
- Four byte-identical original reports plus summary/review are archived in the worktree's `evals/results/2026-09-13-baseline-smoke-v3/`. Step 6 examples: B/dev-01 supported and A/dev-06 inconclusive.
- Results published separately as `9d6a86da0baf96c47707a7aa9fd363d163dfcc0e`; worktree clean. PR #16 is ready for review, with all attached CI checks passing, including hosted integration.
- Post-archive verification: 188 tests passed; lint passed. Offline checks include clean revision, schemas/citations, bounds/costs, original hashes, and unchanged tool evidence relative to batch two.

Both previous allowances remain exhausted: eight requests, estimated $0.00768160. This approval does not permit merging, held-out evaluation, or public hosting.
