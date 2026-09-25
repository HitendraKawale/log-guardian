# Security evidence correlation verification

Issue #48, first offline milestone. Based on e0203d6 plus the changes in this commit.
The owner waived the unavailable Plannotator gate with "just do it". No independent
review, customer traffic, model request or paid evaluation was performed.

## Executed checks

Baseline before implementation: 266 ingestion tests and 279 eval tests passed.
The first 35 security-evidence tests failed because the module did not exist. After
implementation they passed. An additional boundary check then reproduced an uncaught
UTC-conversion OverflowError; the importer now returns a sanitized input error.
The final new coverage is 38 service checks and six eval checks, including eight
hand-authored input cases exercised by the fixture test.

Executed from the feature worktree:

```bash
make test && make test-demo && make lint
```

`local-verification.txt` preserves the full output. Relevant results:

```text
36 passed in 1.35s
304 passed in 20.72s
12 passed in 0.02s
6 passed in 0.06s
285 passed in 14.46s
40 passed in 6.05s
22 passed in 0.49s
6 passed, 2 warnings in 3.61s
All checks passed!
379 files already formatted
VERIFICATION_EXIT=0
```

That is 705 offline tests plus six demo tests. The existing pytest-asyncio configuration
warnings and two demo websocket deprecation warnings remain. No unrelated warning cleanup.

## Executed example

```bash
.venv/bin/python evals/security_evidence.py \
  --config evals/security-evidence/example-owner.json \
  --source gateway=evals/security-evidence/example-gateway.jsonl \
  --source authentication=evals/security-evidence/example-auth.jsonl
```

The complete stdout is `example-report.json`. Checked output:

```json
{
  "records": 6,
  "linked_requests": 3,
  "auth_outcomes": {"failure": 2, "success": 1, "unavailable": 0},
  "collection_complete": null
}
```

The runtime also reports unverified clock alignment, unestablished impact and
unestablished actor/AI attribution. `--help` executed successfully. In-process CLI
tests forbid Python socket creation and runtime reads of the expectation file.
This is not an OS sandbox or proof of behavior under arbitrary process compromise.

## Review and omissions

Self-review checked source ownership, namespace matching, duplicate/conflicting IDs,
ambiguous pairs, bounded reads, safe error output and separation of evaluator data.
No subagent review tools were available. The command consumes normalized records;
a production gateway/auth adapter has not been implemented or verified.

The database, existing ingestion/scorer wire schemas, investigator prompt/tools and
UI were not changed. Docker integration, PostgreSQL and browser suites were not run
for this offline milestone. No deployment, merge or package publication occurred.
The preview and external interview-document corrections remain separate pending work.
