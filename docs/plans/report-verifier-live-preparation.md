# Live verifier preparation

The owner requested the credential-safe driver, execution checks and a local preparation
commit. No push or paid batch start is included in this turn. The previously approved
model and limits remain gpt-4.1-mini-2025-04-14, seventeen requests, no retries,
USD 0.10/report and USD 2 total. A separate explicit batch-start instruction is still
required before invoking the live command.

Status: deferred before implementation when the owner selected the agent-security
product as the next priority. Only this plan exists; no live-driver module, execution
freeze or paid request was created. The completed offline verifier remains experimental.
The next checkpoint commits and pushes that offline work, not a live-ready driver.

## Plan

```text
[frozen wire + clean revision] -> [exclusive shared ledger]
                                      |
[credential guard] <- [durable reservation] -> [bounded request]
                                      |
                            [captured review + usage]
```

| File | Decision |
| --- | --- |
| evals/report_verifier_live.py | New explicit live entry point, credential-suppressing transport, frozen execution manifest and shared-ledger gates |
| evals/tests/test_report_verifier_live.py | Prove credential suppression, no retries, clean/frozen gates and one-shot directory claims with mocked HTTP |
| evals/freezes/report-verifier-execution.json | Freeze source/dependency and exact wire identities after verification; no credentials or evaluator labels |

- [ ] Write failing live-driver tests.
- [ ] Leave the frozen mock adapter and old archives unchanged. Reuse its wire mapping, budgets, usage checks and capture helpers; keep new live orchestration separate.
- [ ] Suppress literal and JSON-escaped credential echoes before the existing capture helper can write them. Suppress malformed or oversized bodies that cannot be safely inspected. Never persist headers or exception messages.
- [ ] Require matching frozen execution digest, clean git status, explicit live flag and a fresh shared-git ledger. Validate credentials before claiming the ledger. No proxy, redirects or retry fallback.
- [ ] Record reservation before dispatch; retain unknown usage as unknown, preserve all eighteen statuses, stop on transport/accounting failures, and keep later cases unattempted.
- [ ] Snapshot runtime sources without evaluator labels, recheck source identity around requests, and reject existing ledgers without resuming.
- [ ] Run mock rehearsal and all affected suites, freeze the execution manifest, then create the authorized local commit and run the non-network preflight from that clean revision.

The first real provider request may still reject this exact structured-output schema.
That consumes an attempt and stops the batch; no retry or schema weakening is allowed.
The one-shot ledger is report-verifier-v2-pilot-01, separate from all closed batches.
Neither a successful dry preflight nor a preparation commit starts the batch.
