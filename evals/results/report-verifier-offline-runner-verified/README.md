# Verified offline runner exercise

No model ran and no spend occurred. Responses were generated from evaluator labels
by ../report-verifier-offline-runner/scripted_driver.py.txt. They are test fixtures,
not independently produced judgments or evidence of injection resistance.

The prepare, replay and score CLI commands all exited successfully. Preparation
produced seventeen eligible request artifacts, excluding the locally invalid v13.
Replay and scoring retained all eighteen cases. The scripted scorecard recorded:

```text
acceptable_passed: 8
negative_substantive_rejected: 9
local_invalid_blocked: 1
required_defects_rejected: 10
verifier_errors: 0
model_execution_verified: false
```

These are deliberately label-shaped outputs, not a measured detection rate. Tests
also cover missing responses, malformed/oversized responses, wrong hashes, false
positive verdicts on negative cases and mismatched defect verdicts. They verify that
errors stay in the denominator and do not count as semantic detection.

Preparation manifest SHA-256:
`3bc448eadf44ab2e5e586509e092cefaf5c6e5cf13146c3f20e97efc31df3b60`.
It binds the exact inputs, prepared requests, implementation files and Python/Pydantic
versions. The largest provider-neutral request is 12,334 bytes. Provider-specific
serialization, deadline handling and billing have not been implemented or tested.

## Commands

From the repository root, choose unused output directories:

```bash
.venv/bin/python evals/report_verifier_eval.py prepare --output /tmp/verifier-prepared
mkdir /tmp/verifier-responses
.venv/bin/python evals/report_verifier_eval.py replay --prepared /tmp/verifier-prepared --responses /tmp/verifier-responses --output /tmp/verifier-replay
.venv/bin/python evals/report_verifier_eval.py score --replayed /tmp/verifier-replay --output /tmp/verifier-score
```

An empty response directory produces seventeen verifier errors and one local block,
not seventeen detected defects. To replay saved outputs instead, put only raw verifier
JSON in files named v01.json through v18.json, excluding v13.json. The commands never
contact a provider or read an API key. There is no live mode.

Preparation and replay never read labels or author scripts. Only the score command
reads pinned labels. Scoring verifies artifact hashes and recomputes decisions from
saved response bytes, rather than trusting stored verdicts. These checks establish
internal consistency, not provider authenticity; replacing response bytes and their
hashes cannot prove that a model generated them.

Response captures stop after 16,385 bytes. Reaching that bound marks the capture
incomplete conservatively, and the 16-KiB response limit rejects it. Original response
files remain untouched. Missing responses have no fabricated output. All output
directories must be new; existing or partially written runs are never resumed.

Full verification: `make test`, `make test-demo`, `make lint` and `git diff --check`.
The suite passed 617 offline tests plus six demo tests. Ruff reported all checks
passed and 370 files already formatted. The two existing demo warnings remain in
verification.txt. The initial CLI reporting failure is retained in the sibling
report-verifier-offline-runner archive rather than overwritten.
