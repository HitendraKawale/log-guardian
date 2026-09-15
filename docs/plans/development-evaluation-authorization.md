# A/B/C development evaluation authorization

The user approved commit/push and 24 development runs on `gpt-4.1-mini-2025-04-14`, at most 64 provider requests and a $0.60 total allowance. Each run receives $0.025. Only A/B/C on dev-01 through dev-08 are allowed, once per pair. No retries or held-out runs.

- Candidate committed/pushed: `ad7f95f0ba86b2a9e0182680dccfb9c1161e51ef`; clean worktree verified.
- Fresh checks: 215 tests passed; lint passed, 70 files already formatted.
- Freeze prompt, schema, model, tools and corpus throughout the batch. Preserve failed runs. Stop on unknown usage, missing artifacts or unexpected cost/request overruns.
- Artifacts and machine ledger: `/tmp/log-guardian-dev-abc.Uv9o3A/`.
- Sequential launcher reserves one request for A/B and six for C before starting each CLI invocation. The ledger records actual observed usage separately. The 24-run allocation exhausts this authorization even if fewer than 64 requests are used.
- State: completed. 24 runs, 46 requests, estimated $0.03470640. All usage known; no retries; no run exceeded $0.025. Ledger and originals archived byte-for-byte in `evals/results/2026-09-14-dev-abc/`, committed as `bbf5980`.
- Results: A 7/8, B 7/8, C 4/8 core review passes. Failures preserved: C model-budget exhaustion (dev-03), C unnecessary abstention (dev-02), C ungrounded diagnosis (dev-04), invalid reports (A/dev-08, C/dev-05), B abstention failure (dev-06). No tuning occurred during the batch.

The user then chose to fix C's tool guidance before freezing (option 1). The `query_logs` description clarification was committed as `998ed13`, and 8 C-only reruns executed within the same $0.60 scope: 20 requests, estimated $0.01367280, all completed with known usage. Core passes rose 4/8 to 5/8; dev-02/04/05 still filter first and abstain unnecessarily. Archived as `evals/results/2026-09-14-dev-c2/` in commit `6a558ee`. Combined development spend this authorization: $0.04837920 of $0.60. The rerun allocation is now also treated as exhausted; further development runs need new approval.

Previous allowances remain exhausted at twelve requests and estimated $0.01177360. No merge, public execution or held-out evaluation is authorized.
