# Offline verifier runner implementation plan

Goal: prepare label-free verifier requests and evaluate saved responses without a live-call path.
Spec: report-verifier-contract-v2.md. Use the existing structural gate unchanged.
Proof: an executable scripted replay, input-separation tests and all affected suites.

```text
[pinned inputs] -> [prepared requests] -> [saved responses + structural gate]
                                                    |
[evaluator-only labels] ----------------------> [offline scorecard]
```

| File | Decision |
| --- | --- |
| evals/report_verifier_eval.py | New prepare/replay/score CLI; no transport or credentials |
| evals/tests/test_report_verifier_eval.py | Test absence of label reads during preparation/replay, local gating, failed-response denominators, frozen bindings and overwrite refusal |
| docs/plans/report-verifier-batch-proposal.md | Explicitly unapproved single-model experiment with new limits and a separate future ledger |

- [x] Write failing tests for prepare, replay and score before implementation.
- [x] Pin v2 input/schema hashes. Prepare eighteen local decisions and seventeen provider-neutral request artifacts. Do not send the local-invalid control.
- [x] Replay only responses named by eligible IDs. Missing, malformed and oversized responses remain verifier errors. Preserve bounded response bytes and mark incomplete captures.
- [x] Score separately using pinned evaluator labels. Report acceptable rejections, known-bad passes, substantive rejections, errors and required-defect targets independently.
- [x] Reject stale preparations and existing output directories. Do not add resume, retries, repair, tools or a network option.
- [x] Draft a new proposal: gpt-4.1-mini-2025-04-14, seventeen requests maximum, one per eligible report, 4096 output tokens/request, 60 seconds/request, USD 0.10/report and USD 2 total. All limits await approval and current pricing verification.
- [x] Run scripted CLI evidence, full tests and lint. Preserve original packet and archives unchanged.

Verification: twelve new runner tests; 617 offline tests and six demo tests passed.
The first CLI exercise found a status-printing error after score output was written.
A regression test now covers the complete CLI sequence; the corrected exercise is
preserved in evals/results/report-verifier-offline-runner-verified/. Both attempts
remain archived and all responses are explicitly scripted, not model-produced.

Core interfaces:

```python
prepare(output: Path) -> dict
replay(prepared: Path, responses: Path, output: Path) -> dict
score(replayed: Path, output: Path) -> dict
```

The request artifacts contain host policy, the exact input object and response schema.
They do not claim provider compatibility, authenticated provenance or successful model execution.
The offline runner reuses check_review rather than duplicating citation/quote validation.
The scorecard keeps transport/protocol errors separate from detected semantic defects.

No production integration, paid calls, commits, pushes or changes to closed allowances.
