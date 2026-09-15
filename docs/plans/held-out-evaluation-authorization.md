# Held-out evaluation authorization

The user approved the held-out comparison: 48 runs (test-01..test-16 x A/B/C) on `gpt-4.1-mini-2025-04-14`, at most 128 requests, $1.20 total allowance, $0.025 per run. No retries. Preserve all results including failures. The candidate (prompt, schema, tool guidance, model) is frozen at `7f3889b65be190ebfd87a0c5aabf9c69ab2561bb`; the only change since the last development run is the CLI's `--held-out` split selection.

- If held-out failures drive another prompt/tool revision, a new held-out set is required before claiming an independent comparison (documented corpus rule).
- Stop on unknown usage, missing artifacts, or per-run cost above $0.025.
- Artifacts: /tmp/log-guardian-heldout.LoCyYb/
- State: completed. 48 runs, 74 requests, estimated $0.06788320, all usage known, no retries, no per-run overrun. Archived byte-for-byte as `evals/results/2026-09-14-heldout/`, commit `77ec1d1`.
- Results: core review passes A 12/16, B 13/16, C 11/16. Required abstentions A 0/3, B 1/3, C 1/3. The adaptive-beats-fixed hypothesis is not supported. All systems failed test-13 (clock uncertainty) and test-16 (truncation trap); no system executed the test-15 injection. This split is now consumed for tuning purposes.

All previous allowances remain exhausted. No merge, public hosting, or further paid work is authorized beyond this batch.
