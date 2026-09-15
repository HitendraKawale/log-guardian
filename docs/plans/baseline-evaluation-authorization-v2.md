# Second baseline evaluation authorization

The user approved committing/pushing the correction candidate and up to four additional requests on `gpt-4.1-mini-2025-04-14`, with a fresh $0.10 total allowance.

- Code revision: `0a97c3f00acdfefe48329f1d0d89a60b3533b59f`, committed and pushed; clean worktree verified.
- Fresh verification: 184 tests passed; lint passed.
- Compare A/B on dev-01 and dev-06 only. No held-out cases, retries, or prompt changes within this batch.
- Each invocation has a $0.025 conservative preflight allowance. Stop on ambiguous usage/billing or an unexpected overrun. Count failed requests toward the limit.
- Artifacts: `/tmp/log-guardian-live-baselines-v2.XcceVY/`.
- Requests consumed: 4 of 4. Estimated costs: A/dev-01 $0.00094240; B/dev-01 $0.00115560; A/dev-06 $0.00080320; B/dev-06 $0.00111080. All returned known usage. Total estimated batch cost: $0.00401200. No further request is authorized.
- Both dev-06 reports still failed to abstain. B retrieved `runbook:timeouts`, but its causal conclusion remained unsupported. Step 6 is not complete.
- All four original reports, summary, and review notes are saved locally under `.worktrees/5-investigation-baselines/evals/results/2026-09-13-baseline-smoke-v2/`, subsequently committed/pushed with the order-only candidate as `8edf09e`. An offline test checks both batches. Fresh verification: 185 tests passed; lint passed.
- Across both authorizations: eight requests, estimated total $0.00768160. Both request allowances are exhausted.

The first authorization remains exhausted at four requests and estimated $0.00366960. This authorization does not permit merging PRs or public hosting.
