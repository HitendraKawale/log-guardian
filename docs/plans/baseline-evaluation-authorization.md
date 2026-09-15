# Baseline evaluation authorization

The user approved up to four live development requests using `gpt-4.1-mini-2025-04-14`, with a $0.10 total allowance, in response to the explicit approval question in this session.

- Limit each invocation to a $0.025 conservative preflight allowance; disable retries.
- Count failed or ambiguous requests toward the four-request limit. Stop on ambiguous billing or an unexpected overrun rather than assuming the request was free.
- Preserve every result, including failures. Use development evidence only; no held-out evaluation is authorized.
- Requests consumed: 4 of 4. All completed with known usage. Estimated costs: A/dev-01 $0.00080880; B/dev-01 $0.00102120; A/dev-06 $0.00070320; B/dev-06 $0.00113640. Total estimated cost: $0.00366960. No further requests are authorized, even though the dollar allowance was not exhausted.
- Both dev-06 reports incorrectly asserted a cause. Required abstentions: 0 of 2. Preserve both as semantic failures, not inconclusive examples.
- All four original JSON artifacts, a summary, and review notes were saved locally in `.worktrees/5-investigation-baselines/evals/results/2026-09-13-baseline-smoke/`. They are not yet committed or pushed.
- Latest credential check: `OPENAI_API_KEY configured: True`. The key value was not printed or copied.
- Artifact directory: `/tmp/log-guardian-live-baselines.sMCxYe/`.
- Selected comparison: A and B on dev-01 (supported) and dev-06 (inconclusive). Labels were inspected offline for selection, never supplied to the runtime runner.
- Verified clean code revision: `e4edf8bdc33e5df6f666518ee146f74a46058e12`. Fresh tests: 177 passed; lint: `All checks passed!`, `66 files already formatted`.

This authorization does not permit merging PRs, public hosting, or additional paid evaluations. Step 5 is complete. Step 6 remains incomplete because neither baseline produced an inconclusive report. No prompt or runtime code was changed between these requests. Further live evaluation requires a new explicit authorization.
