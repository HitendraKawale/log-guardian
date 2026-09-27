# Typed security assessment implementation plan

## Context

The live report accepted an authentication-success claim supported only by gateway HTTP
200 records. Structural validation and citation membership did not catch that error.
Generate recorded facts and mandatory unknowns in code; restrict the model to selections.
Verify the preserved failure cannot render as a recorded authentication success.

Approved for execution. Baseline: pushed commit 3fa9e29 on feat/48-security-live-smoke.
Execution worktree: /Users/hitesh/log-guardian-worktrees/48-typed-security.
Branch: feat/48-typed-security. Initial security investigation suite: 25 passed.
The repository root is on main with unrelated untracked notes; leave it untouched during
implementation. Use an isolated issue-48 worktree based on the execution baseline.
Reference proposal: docs/plans/typed-security-assessment-proposal.md in the existing
48-security-live-smoke worktree. This plan will contain the executable decisions.

## Approach

```text
[saved case] -> [delivered typed evidence] -> [model selects IDs/codes]
                                                    |
[UI: facts / possibilities / unknowns] <- [host validation + templates]
```

Keep the security evidence tool and operational report contract. Change only the security
response schema, interpretation and rendering. Preserve raw historical reports.

### Provider contract

One new module, app/security_assessment.py, owns SecuritySelection and
assemble_security_assessment(selection, batches). It accepts only the retained, redacted
EvidenceBatch objects actually delivered to the model, not arbitrary saved-case lookups.
No new evidence-ID aliases, tool payloads or duplicate fact catalogs.

```diff
- observations: list[Finding]
- likely_cause: Finding | None
- outcome: Literal["supported", "inconclusive"]
- suggested_checks: list[str]
+ focus_evidence_ids: list[str]  # 0..3, each a nonempty string of at most 128 characters
+ hypothesis_codes: list[Literal["repeated_login_attempts", "retry_possible"]]  # 0..2
+ check_codes: list[Literal["read_auth_results", "read_rejection_reasons", "read_session_audit"]]  # 0..2
```

Use strict Pydantic validation, extra=forbid, required lists and duplicate rejection.
Unknown fields, unknown codes, unsupported evidence selections or unmet prerequisites
raise ValueError, reaching the loop's existing invalid_report handling. No repair/retry.
Empty selections are valid; mandatory unknowns still appear.

### Host-owned facts and meaning

- Gateway events generate only recorded time, route, HTTP status and address facts.
  Never generate an authentication outcome from a gateway event.
- Auth events generate the recorded outcome and account reference, when present. Do not
  add a client address from a different event. Separate gateway and auth facts avoid
  silently treating a partner reference as a delivered citation.
- Whole-case summaries generate counts, never identities, actors or causal judgments.
  Page metadata IDs are not selectable factual items.
- Check one case version, deduplicate identical evidence IDs and reject conflicting
  duplicates. Only successful security_case batches can supply factual items. Tool
  errors and partial pages cannot establish absence. Use the whole-case summary for
  statements about zero supplied records; without it, say evidence is unavailable.
- Redacted or missing account identities cannot establish same-account relationships.
  No missing field or unknown event kind may be guessed or silently coerced.

Code prerequisites and wording are fixed:

| Code | Prerequisite | Meaning |
| --- | --- | --- |
| repeated_login_attempts | Whole-case summary reports more than one auth failure | Mistakes and unauthorized guessing are possible explanations; intent is unknown |
| retry_possible | Delivered same-source, same non-redacted account records show a failure before a success in their timestamps | A retry is possible; actor identity and legitimate ownership remain unknown |
| read_auth_results | Summary has zero auth records, or recorded unlinked requests, or no usable summary is available | Obtain scoped auth results; do not presume an auth-service outage |
| read_rejection_reasons | Summary reports auth failures or a delivered auth event records failure | Obtain redacted rejection reasons, not credentials or payload dumps |
| read_session_audit | Summary reports auth success or unlinked requests, or a delivered event records auth success | Inspect session policy and redacted activity records; do not presume compromise |

For retry_possible, use two supporting delivered auth IDs and qualify order as recorded
order, not verified causal order. For summary-based hypotheses use that summary ID.
Prerequisites are applicability checks, not calibrated attack detection. Suggested checks
remain human-readable, read-only instructions, not tools or executable commands.

Persist a host-owned report with schema_version=2, outcome="inconclusive", facts,
hypotheses, unknowns and checks. Facts/hypotheses use the existing Finding-shaped claim
and evidence_ids representation, but the host supplies their text and citations. Unknowns
and checks are host-generated strings. Bound the assembled JSON to 16 KiB and fail closed
on overflow; do not truncate away qualifications or citations.

Always state that collection completeness, real actor identity, compromise and business
impact are unestablished. Preserve the clock-alignment limitation. When the summary has
zero auth records, add "Authentication outcome is unknown; no authentication results
were supplied." With failed evidence reads, state evidence unavailability instead.
These statements must not depend on model-selected facts or checks.

### Integrate without changing other investigation profiles

```diff
- schema = InvestigationReport.model_json_schema()
+ schema = (SecuritySelection if security else InvestigationReport).model_json_schema()
```

In the final-response branch, security runs parse SecuritySelection and call the assembler;
operational runs retain their current report parsing, redaction and citation validation.
Use a standalone security selection prompt, not AGENT_PROMPT plus instructions for an
incompatible report. Preserve tool declarations, initial read, prompt hashing, redaction,
usage accounting and all existing execution budgets.

```diff
- digest({"snapshot": snapshot(case), "question": SECURITY_QUESTION, "workflow": 1})
+ digest({"snapshot": snapshot(case), "question": SECURITY_QUESTION, "workflow": 2})
```

Keep SECURITY_SYSTEM="S". The existing worker checks binding before constructing tools
or calling the provider. A v1 worker must reject a new v2-bound run; a v2 worker must
reject an old queued v1 run. Preserve the existing worker_error result on mismatch,
with zero model calls. Do not migrate, retry or rewrite old runs. Terminal historical
reports stay readable and reopening them remains idempotent and unbilled.

### Version-aware UI

```diff
- render the observations/alternatives/likely_cause fields for every report
+ if schema_version === 2: render host facts, possible explanations, unknowns and checks
+ else if schema_version is absent: render the existing unverified legacy draft
+ else: show unsupported report version without rendering claims as facts
```

Reuse textContent-based elements and citation buttons. Label facts as derived from supplied
records, not independently verified reality. Label hypotheses as possibilities. Preserve
legacy false claims under an explicit legacy-model-draft warning rather than correcting
them. Existing deterministic case review remains available when a model draft fails.

## Reuse

- investigation_security.security_page already provides case-version-bound IDs, normalized
  event kinds, whole-case summaries, partner references and byte-bounded pages.
- investigation_loop.run_agent already retains the exact redacted batches delivered to
  the model and enforces request, tool, token, evidence, deadline and spending limits.
- investigation_security.binding currently includes workflow=1; version the binding when
  changing the report contract so older workers reject new runs before spending.
- investigator.execute_run already checks binding before provider execution and persists
  result["report"] as JSON. No worker persistence rewrite or database migration is needed.
- frontend/security.js already provides safe text rendering and clickable journal citations;
  its renderDraft assumes legacy arrays exist, so version dispatch must precede access.
- tests/security_case_helpers.py and tests/test_security_investigation.py already construct
  real saved cases and scripted SDK responses. The browser suite runs a real worker with
  MockTransport. Reuse these rather than adding a parallel application/test server.
- evals/tests/test_security_live_smoke.py contains a legacy mock provider response. Update
  that test fixture for the new security selection format, not the frozen live runner.

## Files to modify

App and service-test paths below are under services/ingestion-service/.

| File | Today | After |
| --- | --- | --- |
| app/security_assessment.py, new | No typed selection/assembly contract | Own strict selections, prerequisite checks, templates and report assembly |
| app/investigation_security.py | Workflow v1 and free-form report guidance | Workflow v2 and selection-only guidance; existing paging unchanged |
| app/investigation_loop.py | Shared final-report schema and parser | Choose security-only schema/parser; keep operational behavior and limits |
| frontend/security.js, repo root | Legacy fields assumed by renderer | Version dispatch; host facts and possible explanations separated; citations reused |
| frontend/security.html, repo root | Generic model-report copy | Explain v2 selection-only assessment and legacy draft status |
| frontend/investigations.js, repo root | Shared history assumes legacy reports | Approved amendment: render v2 sections and reject unknown versions; operational rendering unchanged |
| tests/test_security_assessment.py, new | No assembler coverage | Typed-fact, code-precondition and hostile-selection regressions |
| tests/test_security_investigation.py | Legacy scripted reports | Real-worker v2 tests, old binding refusal and unchanged guard assertions |
| evals/tests/test_security_live_smoke.py, repo root | Legacy mock provider payload | Selection payload in mock-only rehearsal; live source guards unchanged |
| tests/e2e/test_security_review_ui.py, repo root | Legacy scripted worker/UI assertions | v2 end-to-end rendering, legacy warning, unsupported version and citation tests |
| docs/security-log-review.md, repo root | Existing review/execution contract | Describe narrowed assessment, v1 queue refusal and limits |

Read each changed file fully before its first edit. Existing sources outside these paths,
including normalized evidence schemas, API routes, database columns, operational report
schemas, archived runners and result files, stay unchanged.

## Steps

- [x] At execution time, create an isolated issue-48 worktree from 3fa9e29. Reuse the
  shared /Users/hitesh/log-guardian/.venv. Leave root-main notes, earlier worktrees and
  viewers alone. Record the worktree and branch in this plan.
- [x] Add failing contract tests. Read the archived smoke-03.json unchanged as evidence
  of the old accepted counterexample; reject its free-form response as SecuritySelection.
  For a valid selection of its gateway HTTP 200 ID, assert generated facts describe HTTP
  200, no fact declares auth success, and the mandatory auth-unknown message is present.
- [x] Add parameterized prerequisite/selection tests and implement security_assessment.py
  until they pass. Exercise both allowed and rejected branches for every code. Assert
  fact values and citation sets, not only absence of a forbidden phrase.
- [x] Add failing real-worker tests for selection-only schema delivery and host assembly.
  Switch the security loop schema/parser and replace its incompatible inherited prompt.
  Adapt only security mock responses. Re-run operational tests to detect leakage.
- [x] Test old/new binding mismatch before changing workflow=1 to 2. Both mismatches must
  record failure with zero provider calls. Keep existing cancellation, journal, initial
  read, idempotent promotion and budget tests.
- [x] Add browser assertions for v2 facts, mandatory unknowns, legacy preserved errors,
  unsupported versions, citation opening, hostile text and stale-response isolation.
  Implement version dispatch and reuse the current DOM/citation helpers.
- [x] Update the mock live-smoke test fixture and docs. Keep its closed authorization,
  baseline checks and execution freeze unchanged. No new live candidate is prepared.
- [x] Run full offline and browser verification below, preserve screenshots/logs and
  inspect the diff. Report failures and limitations. Do not commit or push without a
  separate request.

## Verification

Regression matrix:

| Input or attempted selection | Required result |
| --- | --- |
| Gateway 200, no auth | HTTP fact; mandatory unknown auth outcome |
| Gateway 200 plus auth failure | Separate recorded HTTP 200 and recorded auth failure |
| Gateway 401 plus auth success | Separate recorded HTTP 401 and recorded auth success; no compromise claim |
| Auth success followed by order/checkout HTTP 200 | No invented session, order, payment or data-access outcome |
| Summary account count only | Count fact without an account identity |
| Missing/redacted account, ambiguous links, different auth sources | No same-account retry hypothesis |
| Same-source/account failure followed by success | Qualified retry possibility with both actual auth citations |
| Truncated page or error batch | No false whole-case absence or recording-outage assertion |
| Repeated pages | Identical records counted once; conflicts fail closed |
| Unknown/page/cross-case ID, duplicate selection, extra field or arbitrary code | invalid_report; no repair or retry |
| Empty selections | No invented facts; mandatory unknowns remain visible |
| v1/v2 binding mismatch | Zero provider calls; existing worker_error behavior |
| Historical or unknown report version | Explicit legacy or unsupported-version presentation, never v2 trusted-fact rendering |

Run from the execution worktree with OPENAI_API_KEY empty and both tracing environment
variables empty. Run pytest suites from their configured directories:

```bash
(cd services/ingestion-service && /Users/hitesh/log-guardian/.venv/bin/python -m pytest)
(cd evals && /Users/hitesh/log-guardian/.venv/bin/python -m pytest)
make test
make test-demo
make lint
(cd tests && /Users/hitesh/log-guardian/.venv/bin/python -m pytest e2e/test_security_review_ui.py e2e/test_static_demo.py)
```

Use the existing browser suite's isolated ephemeral-port server. Capture desktop/mobile
screenshots of the missing-auth v2 assessment and legacy false claim. Verify source
citations, no browser script errors, keyboard operation, memory-only keys and preserved
consent/execution-key requirements. Additional manual servers, if needed, follow the
named-server rule; never replace a shared viewer or clear its port.

Run all three archived stdlib verify.py.txt scripts and check their existing SHA256SUMS
without rewriting any artifact. Inspect git diff to confirm operational schemas, budgets,
closed ledgers and historical response bytes did not change. Scripted model tests prove
contract enforcement and integration, not the quality of model-selected priorities.

## Approved compatibility amendment

Steps 1 through 7 are implemented in feat/48-typed-security. The planned offline suites,
lint and 14 security/static browser tests passed before a broader consumer check exposed
an omitted renderer. The user approved the one-file compatibility amendment with an
explicit review-gate waiver. Final verification passed 804 offline tests, six demo tests,
lint and 25 browser tests, including the shared renderer and legacy operational flows.

frontend/investigations.js also consumes security reports from the shared investigation
history. Its renderReport reads report.observations.length and crashes on v2. The added
real-browser regression test_v2_security_report_in_shared_investigation_history reproduces
"Cannot read properties of undefined (reading 'length')". Evidence is preserved at
/tmp/lg48-typed-shared-history-red.log. The same regression now passes with version-aware
sections and existing citation helpers.

Approved amendment: include frontend/investigations.js in the file table.
Use version-aware sections for v2 facts/hypotheses/unknowns/checks, an explicit unsupported-
version message, and keep the legacy operational rendering unchanged. Reuse its existing
findingBlock and citation drawer. Run the shared-history regression, the operational
investigation browser suite, and the existing full verification again. Do not change
operational report schemas or API filtering to hide the incompatible data.

Evidence: docs/verification/typed-security-assessment/ in the execution worktree contains
red/green logs, source hashes, desktop/mobile screenshots and historical checksum checks.
There was no independent reviewer or live model test. No commit or push was made.

## Not included

No new dependencies, second model, general entailment engine, new log types, collection
consent changes, automated remediation, attack-accuracy claims or production rollout.
No paid execution, new allowance, automatic retries, merge, commit or push. Independent
review of new evaluation cases remains a prerequisite for later generalization claims,
not a claim this offline implementation can establish.
