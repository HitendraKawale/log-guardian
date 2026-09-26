# Connect saved security evidence to the investigator

Issue #48, based on e0a7926. Implemented and locally verified.
The user waived the unavailable review gate with "just do it" for this milestone.
Use executing-plans for implementation, with the checks below as the task tracker.
Spec: business-security-investigation.md, persistent investigation workflow.

## Goal

The worker currently reads operational logs, not saved gateway/authentication reviews.
An explicit authorized action will queue a case-bound investigation with cited security evidence.
Prove API-to-worker-to-browser behavior with a scripted provider, without paid execution.

```text
[Saved security case] -> [Explicit promotion] -> [Existing queue/worker]
                                                       |
[Human review] <--------- [Bounded agent C] <---- [Case-bound read tool]
```

## Decisions

Reuse the existing queue, worker, report schema, cancellation and journal. Add one read
operation for a saved case. Do not convert authentication outcomes into operational
log levels/messages, and do not build a second agent runner.

Use only system C for this workflow. Store internal discriminator S so an old worker
rejects the run before provider dispatch; the current worker checks the binding and
then calls C. The public API reports C. This upgrade safeguard was added after an
archived-dispatch regression reproduced the wrong-source provider attempt.
 A/B/C operational investigations keep their
existing prompts and tool declarations. The security run exposes only its case reader;
operational logs, metrics and runbooks are not implicitly authorized by matching
service names. A later explicit data-source integration can add them.

A saved case gets at most one investigation in this milestone. Repeated clicks and
uncertain-delivery retries return that run, including after failure or cancellation.
An explicit paid rerun workflow is separate work, not an automatic retry.

## Files

Paths beginning with app/, migrations/ or tests/test_ are under
services/ingestion-service/. All other paths are relative to the repository root.
No new dependencies.

| File | Today | After |
| --- | --- | --- |
| app/models.py | Investigation has no security source binding | Nullable unique security_case_id foreign key |
| migrations/versions/0008_security_investigations.py | Absent | Add binding without losing existing runs or events |
| app/routes/investigations.py | Manual and candidate queue entry points | Execution-key-protected case promotion and public source binding |
| app/routes/security_cases.py | Frozen review response | Also return linked investigation ID, never its model report under the review key |
| app/investigation_security.py | Absent | Case snapshot digest, fixed question, security prompt guidance, bounded evidence projection |
| app/investigation_schemas.py | Log/summary/runbook/metric evidence | Add strict security page arguments, security event kind and case source |
| app/investigation_tools.py | Operational replay/database tools | Owner-bound security snapshot and read_security_evidence |
| app/investigation_loop.py | Operational tool set and initial log query | Select security-only tools/prompt/initial read for a bound case |
| app/investigation_agent.py | Citation membership and observed-kind check | Recognize security events as observed evidence; preserve membership-only limits |
| app/investigator.py | Loads run scope and live operational source | Load/verify the bound snapshot and journal the new tool before dispatch |
| tests/test_security_promotion.py | Absent | Authentication, immutable binding, retry and queue checks |
| tests/test_security_investigation.py | Absent | Projection, pagination, wire delivery, journal and hostile argument checks |
| tests/test_security_investigation_migration.py | Absent | Preserve existing runs/events/logs and reject destructive downgrade |
| tests/test_security_evidence_citations.py | Absent | Delivered security records are observed evidence; page metadata and empty summaries cannot establish a cause |
| frontend/security.html | Deterministic review only | Separate execution key, explicit consent, run status and model draft section |
| frontend/security.js | Upload/history/evidence interactions | Queue/reopen/poll/cancel the linked run and inspect delivered citations |
| frontend/security.css | Review layout | Small additions for draft/run sections and narrow screens |
| tests/e2e/test_security_review_ui.py | Real import API and browser | Add isolated scripted-worker workflow and key/state-switch checks |
| tests/integration/test_security_import.py | PostgreSQL import races | Also verify migration and concurrent case promotion |
| docs/security-log-review.md | Import setup and limits | Document execution consent, worker setup and model-draft limits |
| docs/plans/business-security-investigation.md | Investigator connection remains open | Update only after verification |
| docs/verification/security-investigator/README.md | Absent | Commands, outputs, screenshots and remaining limits |

## 1. Persist and authorize the binding

- [x] Add failing promotion and migration tests before implementing the route.

```python
first = await api.post(f"/investigations/from-security-case/{case_id}",
                       headers=execution_key)
again = await api.post(f"/investigations/from-security-case/{case_id}",
                       headers=execution_key)
assert first.status_code == 201
assert again.status_code == 200
assert first.json()["id"] == again.json()["id"]
assert first.json()["security_case_id"] == case_id
assert first.json()["scope"] == saved_case["report"]["scope"]
assert first.json()["system"] == "C"
```

- [x] Add the database constraint. Do not rely on a browser-generated retry key.

```diff
 class Investigation(Base):
+    security_case_id: Mapped[str | None] = mapped_column(
+        String(36), ForeignKey("security_cases.id", ondelete="RESTRICT"),
+        nullable=True, unique=True,
+    )
```

For SQLite, use its native nullable ADD COLUMN ... REFERENCES form and a unique
index rather than recreating the investigations table. PostgreSQL gets the same
nullable binding and unique index through Alembic operations. Refuse downgrade when
bindings exist. Test with pre-existing investigation events, not an empty database.

- [x] Add the promotion route behind require_investigation_key. Accept no scope,
  question, system or source override. Reject extra body fields through a strict
  empty request model. An absent body is allowed.

```python
class SecurityPromotion(BaseModel):
    model_config = ConfigDict(extra="forbid")
```

New route: POST /investigations/from-security-case/{case_id}, using
Depends(require_investigation_key), the empty SecurityPromotion body above, a
Response for 201/200 selection, and the existing get_session dependency.

Use BEGIN IMMEDIATE for SQLite and SELECT FOR UPDATE on the case for PostgreSQL,
as the existing candidate promotion does. The unique binding is the final arbiter.
An empty execution key disables the endpoint. A security review key alone cannot
queue, inspect or cancel a model run. GET security/cases/{id} may expose the linked
run ID, but not its report, events or execution credential.

- [x] Copy scope only from the saved report. Use a constant host-authored question:

```text
Review the saved gateway and authentication evidence for suspected abuse.
Describe observed requests and outcomes, their correlations, and missing evidence.
Do not assume successful authentication establishes account compromise.
```

Bind request_sha256 to the case snapshot digest, fixed question and workflow version.
The snapshot digest covers the saved report, source_snapshot and input_hashes. The
worker verifies this binding before any provider call. Source registration changes
must not change an already queued case. A missing or mismatched snapshot fails closed.
This detects inconsistent stored state; it is not authenticity against a database owner.

- [x] Preserve the existing pending-queue policy and reject an already-full queue.
  Do not describe that policy as a strict account-wide spending cap. The existing
  different-case PostgreSQL enqueue race is not repaired by a per-case lock.
- [x] Verify disabled/wrong/review keys, unknown cases, rejected overrides, sequential
  capacity, concurrent duplicate promotion, and replay of failed/cancelled runs.
  Assert the HTTP process never invokes a provider client.

## 2. Deliver case-bound evidence through the existing worker

- [x] Add strict arguments. The model cannot name another case, service, namespace,
  source file, table or time window. The selected case is already bounded to one hour
  and four services. This first tool reads that fixed scope rather than widening it.

```python
class SecurityEvidenceQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offset: int = Field(0, strict=True, ge=0, le=1000)
    limit: int = Field(25, strict=True, ge=1, le=48)
```

- [x] Implement a pure page projection in app/investigation_security.py. Inputs are
  the owner-loaded saved snapshot and validated page arguments. Output is an
  EvidenceBatch with source="security_case" and a snapshot version digest.

Each page contains at most 50 evidence items:

1. A stable case summary with saved source-specific counts, confirmed-pair/ambiguous/
   unlinked counts, collection_complete=null, named gaps and limitations. These are
   whole-case counts, explicitly labeled, not counts of the returned page.
2. Page metadata with offset, returned record count and next_offset or null.
3. At most 48 normalized timeline records in saved order, with their source-qualified
   original identity and confirmed partner reference where one exists. Ambiguous
   groups remain ambiguous; do not expand an unbounded group into each record.

Each timeline item has kind="security_event" and an ID made from a SHA-256 digest
of case ID, original source/event identity and snapshot version. Keep IDs below the
report schema's 128-character ceiling. Include original identities in content so
reviewers can trace them back. Page metadata has a query/content-specific ID; do not
reuse an ID with different content across calls.

- [x] Apply the existing credential redactor and 16 KiB result cap to the actual
  serialized batch. Pack a contiguous prefix, stopping at the first record that does
  not fit. Compute next_offset from the records actually included, not the requested
  limit. Include metadata size in the budget. This avoids skipped records under byte
  truncation. Set truncated when records remain. At offset beyond the last record,
  return summary/page metadata and no events, without declaring collection complete.
- [x] Retain the existing 64 KiB total evidence, eight tool executions, six provider
  requests, 120-second deadline, 1024 output tokens, disabled retries and $0.025 worker
  allowance. A 1,000-record case need not fit these limits. State the omitted evidence
  rather than increasing budgets or claiming exhaustive model review.

```diff
 # Only for a worker-bound security case:
+schemas = {"read_security_evidence": SecurityEvidenceQuery}
+initial_name = "read_security_evidence"
+initial_arguments = SecurityEvidenceQuery().model_dump(mode="json")
 # Ordinary runs keep TOOL_SCHEMAS, TOOLS, AGENT_PROMPT and _initial_logs.
```

- [x] Add the method to EvidenceTools and the journal's recordable names without
  adding it to the ordinary model-visible tool list. Use an owner-only initial
  security-read hook analogous to _initial_logs. Record origin="server_initial".
  Preserve committed tool_request before dispatch and request_sequence on completion.
- [x] Load the snapshot through the existing worker's source session. Require system C
  and exact run/case scope binding. Do not fall back to operational logs if the case
  cannot be loaded. No query of the global security_evidence table is needed.
- [x] Build the security prompt from existing safeguards plus explicit limitations:
  HTTP success is not authentication success; authentication success is not compromise;
  addresses are not people; correlation and timing do not establish causation,
  coordination or AI attribution. Saved source configuration is an owner assertion.
  Include the selected prompt and tool schema in the recorded prompt hash.
- [x] Allow security_event in the citation validator's observed-evidence kind check.
  Keep rejecting undelivered IDs and ambiguous ID/content reuse. Do not allow page
  metadata alone to establish a cause. Citation validation still does not establish
  semantic support, and the offline verifier is not silently promoted to production.

- [x] Use the existing scripted_client/MockTransport pattern to inspect the first
  provider request before returning a synthetic report:

```python
assert initial_tool_name == "read_security_evidence"
assert exposed_tool_names == {"read_security_evidence"}
assert observed_auth_outcome == "failure"  # gateway HTTP status is 200
assert other_case_canary not in serialized_provider_messages
assert journal_request_committed_before_tool_dispatch
assert all(len(batch.model_dump_json().encode()) <= 16384 for batch in batches)
```

- [x] Exercise multiple pages, long identifiers, empty cases, missing auth, reused
  request IDs, per-source account counts and truncated evidence. Across pages, assert
  no gaps/duplicates in delivered timeline indices and consistent repeated citations.
- [x] Exercise forbidden case/scope arguments, an operational-tool request, duplicate
  queries, unknown citations, provider failure, missing provider, cancellation, failed
  intent/completion writes and budget exits. Assert no real network transport is used.
- [x] Confirm a successful scripted report persists ordered evidence receipts, source
  binding, prompt hash and usage. Label it a protocol check, not a model-quality result.

## 3. Review and explicit execution in the security page

- [x] Add a separate memory-only investigation-key input and explicit provider-sharing
  consent beside the saved case. Explain that execution sends normalized evidence,
  including addresses/account references, to the configured provider and may spend.
  File upload, history selection and page load must never queue a run.
- [x] Reuse the page's destination validation, redirect refusal and no-store requests.
  Send the execution key only to investigation endpoints, never as a URL parameter.
  Do not redirect users into the old dashboard's locally persisted shared-key flow.
- [x] Capture case ID and connection generation when dispatching. An uncertain response
  retries the same case route. Changing server, key or selected case invalidates pending
  display updates after both fetch and JSON parsing, and stops polling. Connection
  changes abort requests; case/execution-key changes discard in-flight read results.
  Neither action silently cancels an already authorized queued run.
- [x] Reopen the linked run after reload with an explicit execution-key action. Render
  status, model draft, missing evidence and delivered citation snapshots in this page.
  Keep the original deterministic timeline unchanged. Report/citation text uses
  textContent. Mark the report as an unverified model draft even if its outcome says
  supported. Reuse existing endpoint event cursors and stop polling on terminal states.
- [x] Offer cancellation through the existing endpoint. Do not start another run after
  failure, cancellation or a stale claim.
- [x] Extend the browser test's isolated backend with a test-only scripted worker.
  Assert import creates zero runs, review key cannot spend, one explicit click queues
  one run, retries do not duplicate it, citations open recorded evidence, reload works,
  cancellation/failure remains visible, and hostile text does not execute. Check both
  credential inputs stay out of storage and URLs, including after server/case changes.
  The test worker must have no real provider fallback and no reusable runtime fake flag.

## Verification and delivery

- [x] Run initial route, migration, tool and browser checks red, then implement and run
  affected suites. Strengthen the safety checks and reproduce the legacy-dispatch hazard.
- [x] Run make test, make test-demo and make lint from the worktree.
- [x] Run the complete Chromium suite against task-owned API/scorer URLs. Do not use
  default local ports that may target the existing protected stack.
- [x] Extend the existing fresh-database PostgreSQL integration to upgrade from 0007,
  preserve old data, race promotion and confirm one linked run. Check SQLite separately.
- [x] Run the nginx/import integration regressions. Exercise the new browser flow with
  a scripted provider and preserve screenshots and actual tool receipts.
- [x] Verify the historical live candidate still rejects the evolved source, while its
  unchanged archived-source checks pass. Never update frozen artifacts or manifests.
- [x] Update setup/limits and record exact commands/output. Prepare the verified
  milestone for commit/push under the existing issue-48 authorization. No merge or deployment.

## Not included

No paid execution or new live allowance. No automatic detection-to-spend path, new
agent framework, model-parsed raw logs, cross-case search, continuous collector,
production-capacity claim, automated remediation or AI-attacker classifier. No
independent accuracy claim from authored examples or scripted completions. README,
preview and external interview rewrites remain separate work.

## Review state

The previous milestone's hosted CI is successful:
https://github.com/HitendraKawale/log-guardian/actions/runs/36183626878

This session exposed no Plannotator submission tool or executable. The user explicitly
waived that gate. Self-review and executable checks are recorded in
../verification/security-investigator/README.md; no independent review was available.
