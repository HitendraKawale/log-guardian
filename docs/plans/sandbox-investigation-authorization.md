# Live sandbox investigation authorization

The user approved one paid adaptive (C) investigation against the demo sandbox's real logs: one run, $0.025 conservative cap (realistic ~$0.01), model `gpt-4.1-mini-2025-04-14` via the worker's fixed configuration. No retries; a failed run is preserved, not repeated, without new approval.

- Stack: demo compose with `--profile investigations`; worker has `OPENAI_API_KEY` and a random `INVESTIGATION_API_KEY` (not recorded here).
- Procedure: real fault scenario first (owner-only fault port), then one `POST /investigations` (system C) scoped to the incident window. Worker executes; fault reset in `finally` by the scenario.
- Preserve the run row, events, and report as an artifact committed to main, with honest review.
- State: consumed. Run `9d96d8f2-19f7-4778-86e7-e1dcd982672e` completed for an estimated $0.00229760, below the $0.025 cap. No further run is authorized.
- Archive: `demo/investigations/2026-09-14-live-sandbox/`. The worker did not record its code revision; do not infer it from the current checkout.
- Task-owned demo containers were stopped after capture. Recovery was verified before investigation submission, not after the report.
