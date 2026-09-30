# Deterministic security assessment implementation plan

Status: ready for Plannotator review. Implementation waits for approval and exit from plan mode.
This is the review copy of the plan prepared in `48-typed-security`; it governs this change.

## Context

Valid saved evidence currently gets a narrative assessment only after a valid model selection.
The review key should instead open a useful factual assessment without a worker or provider.
Prove repeatable output, zero model calls, and continued access when an optional AI run fails.

The latest synthetic batch produced two completed reports and two rejected selections. Cases 2
and 4 selected source-local record IDs rather than selectable outer evidence IDs. Case 4 also
requested a hypothesis requiring multiple failures when only one was recorded. Preserve those
failures; do not repair their responses or relabel the runs completed.

The user approved a deterministic baseline first. Optional AI prioritization is a later evaluation,
not a prerequisite for this feature. Existing explicitly requested AI investigations stay separate.

Execution baseline: `e912177` in `/Users/hitesh/log-guardian-worktrees/48-typed-security`.
The current root checkout is at `2648747` with unrelated untracked notes. Do not implement on it.
After approval, create `feat/48-deterministic-security` in an isolated worktree from `e912177`,
reuse the shared venv, and copy this approved plan there. Leave the original worktree's untracked
live archive and closure document untouched. No commits, pushes, merge or paid calls are included.

## Approach

```text
[Saved case] → [Deterministic assessment] → [Review page]
      └─────→ [Explicit AI run] ─────────→ [Separate AI status/report]
```

Generate the baseline on a read-only request from the immutable saved snapshot. Reuse existing
redacted evidence projection and typed factual rendering. Apply a versioned display policy in code.
Do not introduce a second parser, a new database report table, or a model fallback/retry mechanism.

The baseline states what supplied records contain. It does not verify their truth, classify an
attack, establish compromise, or identify a person from an address. Outcome remains inconclusive.

### 1. Shared derivation, separate selection

Refactor only evidence derivation inside `security_assessment.py`. Its private result contains
facts indexed by outer evidence ID, eligible hypotheses/checks indexed by code, mandatory unknowns,
and typed event metadata needed for ordering. Keep the public model adapter unchanged.

```diff
-def _assemble(selection, batches):
-    # Validate evidence, derive facts, and select output together.
+def _derive(batches):
+    # Existing typed validation and rendering, without a model selection.
+
+def _assemble(selection, batches):
+    derived = _derive(batches)
+    # Unknown requested IDs or ineligible codes still raise ValueError.
+
+def build_security_baseline(saved: dict) -> dict:
+    # Read the saved snapshot and apply deterministic display policy.
```

Preserve `SecuritySelection`, its three-fact/two-hypothesis/two-check limits, the existing
`assemble_security_assessment` interface, its rejection behavior, and its 16 KiB report cap.
The baseline can show more facts without relaxing the model's schema. A rejected model selection
never goes through the baseline builder.

### 2. Scan all saved records, not just the first model page

`build_security_baseline(saved)` consumes the existing `snapshot(case)` dictionary. It has no
network, database, provider credential, clock or mutable source-registry dependency.

Use `security_page` and `SecurityEvidenceQuery` with 48-record pages. Follow `next_offset` until
the saved timeline is exhausted. Respect the existing 1,000-record import bound.

Reject page errors, nonadvancing offsets, mixed versions, conflicting evidence, inconsistent
record counts or incomplete exhaustion. Deduplicate identical repeated summaries; page metadata
is not a fact. Validate full coverage before combining evidence for derivation. Intermediate
`truncated=true` means another page existed; it must not create a false incomplete-scan warning
after successful exhaustion. Collection completeness outside this saved case remains unknown.

This local scan does not expand the model's six-request/eight-tool/64 KiB evidence budget.
It never enters the model tool loop.

Return an envelope around the existing v2 report shape:

```json
{
  "method": "deterministic",
  "policy_version": 1,
  "case_version": "snapshot digest",
  "report": {"schema_version": 2, "outcome": "inconclusive", "facts": [], "hypotheses": [], "unknowns": [], "checks": []},
  "coverage": {"saved_records": 0, "reviewed_records": 0, "displayed_event_facts": 0, "omitted_event_facts": 0, "fact_limit": 12, "display_limited": false},
  "evidence": []
}
```

The evidence list contains redacted summary/events cited by displayed facts or hypotheses only.
Include hypothesis citations even when those events are absent from the displayed fact list.
Coverage counts unique saved timeline records, not raw duplicate deliveries or evidence summaries.

### 3. Explicit selection policy, not an attack score

Policy version 1 chooses at most 12 facts, including the summary:

1. Whole-case summary.
2. Both records supporting the earliest eligible retry pair, if present.
3. One representative per observed auth outcome, ordered failure, success, unavailable.
4. One representative per gateway HTTP status, ordered 5xx, 4xx, 3xx, 2xx, 1xx, unavailable.
   Numeric status breaks ties within each class.
5. Fill remaining slots from other auth records, then gateway records.

Use parsed timestamp, source ID and source-local record ID for stable representative/fill ordering.
Deduplicate before taking the display prefix. This is presentation order, not causal order or risk.
Use the existing retry eligibility and pair-selection semantics so old model reports do not change.

Include applicable existing hypothesis templates, at most two. Choose baseline checks in this order:
- Rejection reasons when recorded authentication failures exist.
- Session policy/audit when recorded success or unlinked requests exist.
- Authentication-result records when none were supplied.

Unlinked catalog/cart records alone do not trigger the last check or prove a telemetry defect.
This stricter baseline choice does not change the old model adapter's accepted codes. Do not infer
login routes from URL strings or add owner configuration for this slice.

Keep the baseline report within 16 KiB and the complete response envelope within 64 KiB, measured
using the serialization actually returned. Reduce the selected fact prefix deterministically if
needed and disclose omissions with `display_limited=true`. Do not truncate strings or citation
bodies. If mandatory summary, unknowns, applicable hypotheses/checks and citations cannot fit,
return an explicit failure while leaving the saved evidence readable. Do not silently drop limits.

### 4. Review-only endpoint, no persistence changes

```diff
+@router.get("/cases/{case_id}/assessment")
+async def get_assessment(case_id: str, response: Response,
+                         session: AsyncSession = Depends(get_session)):
+    case = await session.get(SecurityCase, case_id)
+    if case is None:
+        fail(404, "Unknown security review")
+    try:
+        assessment = build_security_baseline(snapshot(case))
+    except ValueError:
+        fail(422, "Saved evidence cannot produce a bounded assessment")
+    response.headers["Cache-Control"] = "no-store"
+    return assessment
```

Reuse the router's review-key authentication. Normalize malformed snapshot/derivation failures to
`ValueError` at the builder boundary without exposing evidence in error messages. Do not catch
unrelated programming errors broadly. No Investigation creation, worker call or stored-report update.
Existing import and case-detail response shapes remain unchanged.

Baselines are derived using the reported policy version, not frozen historical model outputs.
Future policy revisions must be explicit; same snapshot and same policy yield identical output.

### 5. Separate baseline and AI state in the browser

```diff
+<section aria-labelledby="security-assessment-title">
+  <h3 id="security-assessment-title">Factual assessment</h3>
+  <p id="security-assessment-status" role="status" aria-live="polite"></p>
+  <div id="security-assessment-report"></div>
+  <details><summary>Assessment evidence</summary><div id="security-assessment-evidence"></div></details>
+</section>
 <section class="security-execution" aria-labelledby="security-run-title">
```

After import or case selection, fetch the assessment using the review key. Label it "Generated by
deterministic rules. No model call." Show counts reviewed/displayed/omitted and the evidence limits.
No execution key or sharing consent is needed for this local report.

Reuse report rendering with an explicit root and evidence map per caller. Keep baseline state
independent of `resetRun`. Changing the execution key or receiving an invalid report, provider error,
budget failure or cancellation must not clear it. The optional AI run retains its actual status.

Use existing connection-generation/detail-version guards to discard stale responses. Clear baseline
content on case/connection changes. Keep text-only rendering, keyboard citations, memory-only keys,
mobile layout and refusal to render unsupported versions. A baseline fetch error must not hide the
saved timeline or suggest that a model call is necessary.

Shared investigation history gets a link to `security.html?api=<origin>&case=<case-id>` when the run
has a security case. Open that case only after review-key authentication, without requiring it to be
in the first history page or requiring a current source registry. Separate source-loading errors
from the saved-case deep-link read. Never include keys in the link or borrow the execution key.
Historical AI reports remain unchanged; this link does not embed baseline data under other permissions.

## Files to modify

All implementation paths are relative to the new execution worktree.

| File | Today | After |
| --- | --- | --- |
| `services/ingestion-service/app/security_assessment.py` | Typed rendering depends on model selection | Shared derivation plus bounded deterministic saved-case builder; strict model adapter preserved |
| `services/ingestion-service/app/routes/security_cases.py` | Import/history/snapshot reads | Additional review-only assessment GET; no writes |
| `frontend/security.html` | Narrative appears in optional AI section | Independent factual assessment above AI controls |
| `frontend/security.js` | Saved evidence and AI rendering | Independent baseline request/state/citations, coverage and authenticated case deep link |
| `frontend/investigations.js` | Failed security runs may have no report | Permission-preserving link to the saved case review |
| `services/ingestion-service/tests/test_security_baseline.py` | Absent | Pure builder and policy regression tests |
| `services/ingestion-service/tests/test_security_cases.py` | Import/auth/idempotency tests | Assessment auth, no-spend, snapshot and failure-independence checks |
| `tests/e2e/test_security_review_ui.py` | Real API/SQLite with optional scripted worker | No-worker baseline, AI-failure separation, deep-link/citation/stale-response checks |
| `docs/security-log-review.md` | Documents model-selected assessments | Baseline endpoint, versioned policy, coverage and separate optional AI behavior |
| `docs/verification/deterministic-security-assessment/README.md` | Absent | Actual commands, results, screenshots and limitations |

## Reuse

- `snapshot`, `security_page`, `digest` in `app/investigation_security.py`: immutable case version,
  stable citations, redaction and contiguous byte-bounded projection.
- `SecurityEvidenceQuery`, `EvidenceBatch`, `Finding` in `app/investigation_schemas.py`: existing types.
- Typed `GatewayEvent`/`AuthEvent`, `_finding`, prerequisite checks and unknowns already used by
  `app/security_assessment.py`: no parallel interpretation of HTTP or authentication outcomes.
- `fail`, `require_security_key`, `get_session` and router dependencies in
  `app/routes/security_cases.py`: authentication, sanitized errors and no-store responses.
- `element`, request-generation guards, `renderDraft` and citation maps in `frontend/security.js`:
  safe rendering and cancellation/staleness handling.
- Existing `configured`, `client`, `session_factory`, `security_stack`, `connect` and `upload_example`
  fixtures/helpers. No new testing framework or generic service abstraction.

## Steps

Use executing-plans inline after approval. No subagent tool is available.

### 1. Pure baseline

- [x] Create the isolated execution worktree only after plan mode ends. Read touched files fully.
- [x] Add a failing `build_security_baseline` test using `analyze_import(OWNER, payload())` from the
  existing security helpers. Build the snapshot dictionary with a fixed case ID and SHA-256 input
  hashes. Assert repeated output equality and no input mutation. Assert HTTP 200 and auth failure
  remain distinct facts, with no invented auth success.
- [x] Refactor shared derivation and implement the deterministic policy. Run the original selection
  tests unchanged to preserve all invalid-ID/code, version, redaction and byte-limit rejections.
- [x] Exercise all four committed `evals/typed-business-live/inputs.json` cases. Assert every record
  was reviewed, citations resolve, case 3 retains unknown auth, and case 4 has no repeated-failure
  hypothesis. Do not depend on the untracked latest live archive for CI tests.
- [x] Add multi-page and 1,000-record cases, outcome representatives, timestamp ties, redacted
  identities, empty inputs, conflicting evidence, broken offsets, and long Unicode fields.
  Verify exact coverage/omission counts and both serialized size limits.

### 2. Read-only endpoint

- [x] Add a failing endpoint test with `settings.investigation_api_key=''`. Import using the review
  key, GET the assessment twice, assert identical JSON/no-store and zero Investigation rows.
  Trap provider dispatch so any accidental model access fails the test immediately.
- [x] Implement the endpoint and verify review-key disabled/wrong/missing behavior, 404, sanitized
  422, current-registry changes/deletion, and existing failed/cancelled AI runs. Assert no run,
  report, event or case-row mutations. Baseline output stays identical across AI state changes.
- [x] Run the full ingestion, contract and eval suites before UI work.

### 3. Baseline-first UI

- [x] Add the no-worker browser regression with `security_stack='idle'`: import via the real API,
  see factual assessment before consent, leave execution key blank, and assert zero investigations.
- [x] Implement independent loading/rendering and citations. Add scripted invalid-selection and
  provider-error checks: AI report absent, run failed, baseline unchanged. No live model calls.
- [x] Exercise stale case/key/API responses, malicious text, keyboard citations, empty browser
  storage, reload, unknown versions and 390px mobile rendering. Verify baseline-fetch errors leave
  the timeline usable and do not queue work.
- [x] Add the shared-history link and test its review-key-gated deep link, including a case outside
  the first page and an unavailable current registry. Assert no key in URLs or forwarded headers.
- [x] Scope existing "Recorded facts" assertions to the intended panel. Narrow existing
  `/security/cases/*` test interception so assessment responses are not treated as case snapshots.
  Preserve legacy model claims as legacy, even while the separate factual baseline remains visible.

### 4. Documentation and proof

- [x] Document the policy, endpoint, coverage, derived-not-persisted behavior and product limits.
- [x] Run the verification below and preserve red/green output, source hashes and desktop/mobile
  screenshots. Name failed or blocked checks; do not overwrite prior evidence.
- [x] Open implementation diff review when available. Do not commit, push, deploy or spend without
  separate authorization.

## Verification

Run from the new worktree with provider credentials disabled:

```bash
export OPENAI_API_KEY='' OTEL_CONSOLE='' OTEL_EXPORTER_OTLP_ENDPOINT=''
make test
make test-demo
make lint
cd tests
../.venv/bin/python -m pytest e2e/test_security_review_ui.py e2e/test_static_demo.py e2e/test_investigations_ui.py -q
```

The full ingestion suite must cover unchanged model selection/worker/journal behavior as well as the
new builder and endpoint. Browser checks must use the running API, saved SQLite records and real UI,
not just render mocked JSON. Provider failure tests use scripted transport only.

Replay preserved archive verifiers/checksums without modifying their bytes. Verify the latest
untracked batch in its original worktree rather than moving it into the feature branch. Demonstrate
zero outbound provider requests and zero new Investigation rows in the default review flow.

These checks establish deterministic behavior and independence from model failure, not production
capacity, independent detection accuracy or overall production readiness.

## Not included

Fine-tuning, model upgrades, a new AI-ranking protocol, automatic repair/retry, changed paid budgets,
attack verdicts, migrations, new dependencies, tenant isolation, retention, continuous collection,
production deployment and independent quality evaluation are separate work. The deterministic
baseline is the first useful product increment, not a promise that supplied evidence is true.
