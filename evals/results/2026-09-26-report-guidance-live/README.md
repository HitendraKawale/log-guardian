# Report-guidance live repeat: formatting improved, semantic failure remains

All four reports completed and passed structural validation. That is not four correct
diagnoses. The missing-authentication case now calls a gateway HTTP 200 a "successful
login attempt" despite having no authentication records. This accepted false inference
is the main remaining failure, and it is preserved unchanged.

The security-report-guidance-2026-09-26-03 allowance is closed. No retries, response
repairs, extra model calls, push or production deployment followed.

## Results

| Case | Scenario | Worker result | Output tokens, prior → repeat | Estimated USD |
| --- | --- | --- | ---: | ---: |
| smoke-01 | Suspicious login failures, catalog/cart traffic, unpaired 429 | Completed, inconclusive | 830 → 802 | 0.00297440 |
| smoke-02 | Two failures then success, ordinary-retry-shaped traffic | Completed, inconclusive | 1024, truncated → 574 | 0.00217360 |
| smoke-03 | Gateway requests, no supplied auth records | Completed, inconclusive; unsupported login-success claim | 804 → 496 | 0.00179320 |
| smoke-04 | Auth success, later order/checkout requests with unknown effects | Completed, inconclusive | 888 → 696 | 0.00237080 |

Four requests returned HTTP 200 and finish_reason=stop. There were no follow-up model
tool calls. All 35 supplied records arrived through four initial read_security_evidence
calls, without evidence-page truncation. All citation IDs in the reports were delivered.

Usage: 13,008 input tokens and 2,568 output tokens; zero cached input tokens reported.
Estimated cost and uncached upper estimate: USD 0.0093120. Conservative reservations:
USD 0.03648400, within USD 0.025 per case and USD 0.10 total. Usage is known for every
request. These numbers estimate cost from returned usage; they are not a billing receipt.

The prior batch accepted one report, rejected two incoherent outcomes, and rejected one
truncated response. This repeat accepted four complete reports, each with likely_cause=null
and outcome=inconclusive. Each has three observations, one alternative, three evidence
gaps and two suggested checks. The soft target of six citation occurrences was not met:
the reports contain 14, 8, 7 and 11 occurrences respectively. Brevity guidance is not a
hard output constraint or a guarantee of future completion.

## Semantic review, not an accuracy score

The fixture author also reviewed these outputs. There was no independent reviewer.

### Missing-auth case: an accepted unsupported authentication claim

smoke-03 observation 3 says:

> The gateway requests included one successful product catalog fetch (HTTP 200), one successful login attempt (HTTP 200), one failed login attempt (HTTP 401), and one service unavailable response (HTTP 503) for login.

The cited items are gateway events. The saved summary has auth.records=0. HTTP status
alone does not establish an application authentication outcome, so the successful-login
wording exceeds the evidence. No successful authentication can be concluded from this
case. Calling the report inconclusive does not make that observation safe or supported.

The same report says no authentication results were "recorded" and suggests events were
not collected properly. The data establishes no supplied authentication records, not
proof of a service-side recording failure. The previous version's accepted report did
not make this explicit successful-login claim. Keep this regression in the comparison;
do not replace it with a paraphrase that only describes HTTP success.

### Valid identifiers still do not prove claim-level support

- smoke-01 claims all six correlated login requests returned HTTP 401. Its citations
  include a count summary, four auth records and only three gateway records. The other
  gateway records are delivered elsewhere, but this claim's references do not directly
  support the HTTP status of every request it describes.
- smoke-02 names client address 192.0.2.44 in a claim citing only three auth events.
  Those cited records have partner references but no client_address field. Gateway
  events carry the address, and are cited in another observation, not this one.
- smoke-04 correctly avoids declaring an order, payment or compromise. Its alternative
  for unlinked requests lists unauthenticated access or missing telemetry, but does not
  acknowledge ordinary session handling without a separate auth-result event on every
  route. Unlinked events alone do not establish either proposed explanation.

The reports still request detailed headers/payloads. Any manual follow-up requires
privacy-safe scoping; these suggestions do not authorize credential collection or
additional sharing with a provider. No suggested action was executed.

The observed improvement is report completion and outcome consistency on these cases.
Semantic reliability has not been established. Do not treat structural acceptance,
valid citation membership or a final inconclusive label as an entailment check.

## Freeze and comparison limits

Application candidate: 147444fdada01becc86415d5a5ab58ee30eba4de.
Local execution-freeze commit: f137767.
Preparation SHA-256:
491b8f2282e604a6d83bbb4870da79b46ec9b082b9a0dd84741b2eee6c4359d5.

Relative to the prior application candidate, only SECURITY_GUIDANCE changed in
application code. The input log bytes, owner source registry and dependency versions
match the preceding business batch. Model, validators, evidence-ID generation, native schema
ordering, output-token ceiling and retry limits are unchanged. Captures confirm that
all four actual system messages contain the updated guidance.

This is a single repeat on development cases already seen and used for tuning. Case
UUIDs and derived evidence IDs change with each import. It is not an independent
benchmark, a multi-sample experiment or proof of a causal effect size. Do not report
4/4 acceptance as detection accuracy or production readiness.

Offline preflight: 766 tests, six demo tests and lint passed. The mock rehearsal delivered
15/8/4/8 records. Those checks establish integration and safeguards, not model quality.

The actual FastAPI routes ran through ASGITransport and the actual run_once worker used
one isolated SQLite database per case. Only the provider was live. No real business,
customer traffic or live login system was attacked. No continuous provider worker was
started. This does not exercise production process separation, concurrency or capacity.

## Evidence

The original 61 ledger files are preserved. Source/JSON files are byte-for-byte copies;
SQLite files are compressed with their decoded bytes verified. original-files.json
records original hashes; manifest.json and candidate/ preserve the execution snapshot.
request_json stores exact sent UTF-8 bodies; request_sha256 binds those bytes. Provider
headers and credentials are not archived. Raw model content, including incorrect claims,
remains unchanged. analysis.json contains the offline inspection, not an independent grade.

Replay the captured facts without a key or network:

```bash
python evals/results/2026-09-26-report-guidance-live/verify.py.txt
```

## Read-only product inspection

http://127.0.0.1:8486/ serves copies of this batch's databases through the unchanged
security UI. /tmp/lg48-guidance-viewer.py uses pinned loopback port 8486, with no provider
key or worker. It leaves the earlier views on ports 8484 and 8485 untouched. Portless
would require privileged proxy setup, so the loopback fallback avoids shared proxy changes.
Review/execution keys are in owner-only /tmp/lg48-guidance-viewer-runtime.json.
Use Chromium for the linked smoke-*.localhost case URLs; the plain loopback UI defaults
to smoke-03. All write methods return 405, so inspection cannot queue new execution.

The browser check opened all four stored reports and a citation in each. It explicitly
confirmed that smoke-03 displays the unsupported successful-login wording rather than
silently correcting it. Empty browser storage, write refusal and no page errors were
verified. ui-verification.txt, ui-smoke-*.png and the helper scripts preserve the checks.
The landing page warns that structural acceptance did not remove semantic errors.

The verifier explicitly retains the combination of zero auth records and the accepted
successful-login claim. Historical batch files, recorded numbers and closed ledgers were
not rewritten. Further live testing requires a new authorization; do not spend remaining
request slots or reservations from this batch.
