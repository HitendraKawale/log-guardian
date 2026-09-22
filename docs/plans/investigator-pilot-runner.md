# Investigator pilot runner

Use the existing worker, tool journal and SQLite model tables. Add accounting at
the HTTP transport boundary so raw model tool proposals survive pre-dispatch
rejection. Do not modify prompts, schemas, scope enforcement or worker budgets.

```text
[Native worker] -> [Fsynced request reservation] -> [Official model endpoint]
                                                        |
[Tool journal] <- [Native dispatch] <- [Fsynced response witness]
```

| File | Decision |
| --- | --- |
| `evals/investigator_pilot.py` | Dry-run default; frozen-candidate and clean-worktree gates; one shared authorization ledger; bounded recording transport; one isolated SQLite database per case |
| `evals/tests/test_investigator_pilot.py` | Use the actual SDK, worker and tools with mocked HTTP; prove write ordering, one-shot refusal, accounting and failure stops |
| `docs/plans/investigator-pilot-authorization.md` | Preserve the owner's USD 2 total authorization and unchanged per-case/request limits |

The email pilot's fsync/exclusive-create pattern is reusable, but its runner depends
on AgentDojo and a consumed allowance. Do not import it or reopen its ledgers.
No new dependency or application abstraction is needed.

## Runtime decisions

- Candidate fingerprint covers the runner, tests, input fixtures, authorization,
  production source, runbook and installed dependency versions. Reviewer notes
  are not opened by the runner. Production source hashes must still match a0d0df4.
- Live execution requires the matching digest and a clean worktree. Store output
  only under the shared git directory, not inside the worktree during execution.
- The recording transport accepts only POST /v1/chat/completions on api.openai.com,
  the authorized model, store=false, 1024 output tokens and the native request shape.
  Add service_tier=default to prevent inherited project pricing. Require the response
  to confirm that tier. Disable SDK/transport retries, redirects and environment proxies.
- Limit request bodies to 128 KiB. Reserve using body bytes plus 4096 overhead
  tokens at the pinned non-cached rates, plus the 1024-token output ceiling.
  Never refund reservations. Enforce both case and batch limits before sending.
- Preserve successful response bodies before SDK validation/tool dispatch. Never
  save request headers or credential-bearing error bodies. Check usage types,
  totals, token bounds and model. Failed or cancelled sends consume their slot.
- One database per case avoids mixing identical service/time scopes across pairs.
  Seed the authorized fixture plus one synthetic inventory canary outside scope.
  Save the fixture-to-database evidence-ID mapping for later grading.
- Run execute_run unchanged. No Prometheus source may be configured. Archive the
  run row, journal and scope review after each case; do not infer complete capture
  from the journal alone. Raw response witnesses preserve unknown/malformed calls.
- Stop on ledger/transport failure or ambiguous worker interruption. Normal agent
  failures such as unknown_tool or invalid_report stay in the denominator.

## Checks

- [x] Observe missing-runner tests fail before implementation.
- [x] Exercise ten scripted cases through the real SDK/worker and verify one-shot
  refusal, zero label reads, no canary exposure and request/completion linkage.
- [x] Assert reservations exist before HTTP and response witnesses before dispatch.
- [x] Inject HTTP failure, timeout, bad usage/model, write failure and candidate
  drift; verify no retry or later case executes after an ambiguous failure.
- [x] Check request, body-size and reservation ceilings before sending.
- [x] Run full offline suites, lint and default CLI preview. No live execution yet.

Prices were checked against current official model documentation through Context7;
see investigator-pilot-pricing.md. The byte-based bound is conservative engineering
accounting, not an account-wide provider billing cap. No automatic semantic grader
or independent-review claim is added in this change.

## Verification checkpoint

24 runner checks passed. The full offline suites passed 506 tests, plus six demo
tests; lint passed. A separate scripted rehearsal completed all ten cases using
20 fake provider responses and real worker/SQLite tool execution. No provider call
was made, and the live authorization ledger does not exist yet.

The tests also cover compressed responses and literal/JSON-escaped credential echoes.
Candidate drift during a response stops dispatch as well as later sends. The initial
red logs and final suite log are under `/tmp/lg40-pilot-*.log`.

Frozen candidate: `57bddee278208dac2c489b050649cfca44126cfc47784840b01f379043ec9502`.
Manifest: `evals/investigator-security/pilot-freeze.json`.
Scripted evidence: `evals/results/2026-09-22-investigator-pilot-scripted/`.

The next gate is explicit local commit approval. No commit, push or live run was
performed. After an approved commit, recheck the digest, clean worktree, credentials
without revealing them, and absence of the live ledger before claiming this batch.
