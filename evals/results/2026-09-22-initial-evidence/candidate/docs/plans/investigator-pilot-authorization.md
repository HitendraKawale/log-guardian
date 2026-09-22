# Investigator security pilot authorization

The owner approved a self-authored pilot, with independent review still pending,
and raised the total allowance to USD 2.00 on 2026-09-22.

- Authorization ID: investigator-security-pilot-2026-09-22
- Model: gpt-4.1-mini-2025-04-14, official OpenAI endpoint only.
- Cases: stage-01 through stage-10, exactly once each. Five benign/attack pairs.
- Request ceiling: six per case, sixty across the batch, including failed attempts.
- Per-case ceiling: USD 0.10. Total ceiling: USD 2.00. Raising the total ceiling
  does not raise the per-case ceiling; ten per-case allowances sum to USD 1.00.
- The unchanged worker retains its stricter USD 0.025 preflight budget per run.
- No retries. Stop the batch on provider/accounting ambiguity, unknown usage,
  model mismatch, storage failure, candidate drift or an interrupted run.
- Reserve conservatively before each send, without cache discounts. Keep unknown
  usage unknown; never reopen the allowance or silently retry a failed case.
- Inputs: the existing unreviewed draft, cases.jsonl SHA-256
  5d720e4c8af1f7d634f700de5574a36a2d6ed10e6c42072c4cdeb999e0f1dcca.
- Production implementation remains the one in a0d0df4. The exact runner, runtime
  files, dependencies and input hashes must match an explicit candidate digest.

No prior email, Jev or investigator allowance is reused. No independent accuracy
claim, production traffic, commit, push or PR publication is authorized here.

Execution is still gated on offline verification, current price verification,
a frozen candidate and a clean committed runner. Commit approval is separate.
The candidate manifest's hashes bind the implementation; the live ledger also
records the actual committed revision. Reviewer notes remain evaluator-only.

The live ledger belongs under the shared git directory, using this authorization
ID. Exclusive directory creation permits one claim across worktrees. Dry runs
and scripted tests must not claim that directory or spend any of this allowance.
