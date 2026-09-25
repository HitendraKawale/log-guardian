# Security evidence correlation: first implementation milestone

Issue #48, branch feat/48-business-security.
Status: implemented and locally verified. The owner explicitly waived the review gate
with "just do it" for this milestone.
Spec: [business-security investigation](business-security-investigation.md).

## Goal

Current logs lack typed request and authentication evidence.
Build an offline, bounded timeline that links explicitly related gateway/auth records and preserves ambiguity.
Prove counts, links and evidence gaps with synthetic fixtures, including benign counterexamples; do not claim attack detection accuracy.

```text
[Owner source settings] -- identity + namespace --> [Validated records]
                                                        |
[Normalized JSONL] -------------------------------------+
                                                        v
[Offline check] <------- [Timeline + gaps] <--------- [Exact-ID groups]
```

## Decisions to review

### Separate record identity from correlation identity

The Compose forwarder already chooses service identity from host configuration, not
embedded JSON. Reuse that principle, not its plaintext parsing. It does not currently
preserve the structured security fields this milestone needs.

```diff
- correlation_key = (source_id, request_id)
+ evidence_key = (source.source_id, event.evidence_id)
+ correlation_key = (source.request_namespace, event.request_id)
```

SourceConfig owns source_id, service, event_kind and an optional request_namespace.
The event body cannot override them. Only configure a shared namespace when trusted
infrastructure assigns unique request IDs and propagates them between those sources.
If that guarantee is absent, configure no namespace and report unlinked evidence.
An event saying it is trusted is not evidence of trust.

Account counts are per authentication source. Cross-source account equivalence is
not assumed. Address counts use the configured gateway source's observed address;
an address is not a person or agent. No forwarded-header interpretation in this slice.

### A normalized input contract, not a production adapter

Use the already installed Pydantic library for strict, frozen input models with
extra fields forbidden. Use stdlib JSON decoding with duplicate-key and nonfinite
number rejection. Source configuration is a separate owner input, not part of JSONL.

```python
inspect_bundle(config: dict, inputs: dict[str, bytes]) -> dict
# Internal stages keep typed source configuration attached to every event:
parse_events(raw: bytes, source: SourceConfig, scope: InvestigationScope) -> list[SecurityEvent]
correlate(events: list[SecurityEvent], config: BundleConfig) -> dict
```

Gateway bodies contain evidence_id, event_time, optional request_id, normalized
route, optional client_address and optional http_status. Auth bodies contain
evidence_id, event_time, optional request_id, optional account_ref and auth_outcome.
The parser attaches owner-supplied source identity, service, kind and namespace.
No message, header, credential, body, prompt or arbitrary metadata field is accepted.
Do not serialize Pydantic error details containing rejected input into output reports.

Validate address syntax with stdlib ipaddress. IDs use bounded printable ASCII tokens;
route begins with `/` and contains no query, fragment, whitespace or control characters.
HTTP status is a strict integer in 100..599. Auth outcome is success, failure or
unavailable. Timestamps must carry offsets and normalize to UTC. Missing values remain
missing rather than being invented from HTTP status or message text.

Use the existing four-service, positive-at-most-one-hour scope. Limit the entire
bundle to four sources, 1 MiB input bytes, 1,000 input records before deduplication,
and 16 KiB per line. Read only limit + 1 bytes to detect oversized files. Reject
out-of-scope events and limit violations explicitly; do not silently truncate.

### Count evidence before inferring attempts

```diff
- attempts = number_of_log_lines
- successful_login = http_status == 200
+ observed_auth_results = count_unique_auth_records
+ confirmed_links = groups_with_exactly_one_gateway_and_one_auth_record
+ observed_login_success = auth_record.auth_outcome == "success"
```

Deduplicate identical canonical records with the same evidence_key. Reject the whole
bundle if the same key has different canonical content. Do not deduplicate on request
ID: reuse of that ID is evidence of ambiguous correlation.

One gateway and one auth record in an authorized namespace form a link. Any additional
record in that group makes it ambiguous: retain every record, cite them, and omit the
confirmed link. Unmatched or missing-ID records remain visible. A success without a
gateway link is still an observed auth success, but its origin remains unresolved.

A source-time sort is a display order, not proof of causal order. For a linked pair,
a gateway timestamp is not assumed to be request start: many access logs record
completion. Always name unverified clock alignment as a limitation. Do not reject
valid links merely because source timestamps appear reversed.

### Output observations, not a model verdict

Return the normalized source-time timeline, exact evidence references for confirmed
links and ambiguous groups, source-specific counts, observed auth outcomes, unlinked
records and named gaps. Always state that collection completeness is unknown and
successful authentication does not establish account compromise or data access.
An empty import means no evidence supplied, not no attack.

No confidence score, credential-stuffing classification, attribution, automatic action
or provider request. The user may investigate a credential-stuffing hypothesis without
the system prematurely confirming it. Future summaries must cite these observations.

## Files

| File | Today | This milestone |
| --- | --- | --- |
| services/ingestion-service/app/security_evidence.py | Absent | Input validation, owner source configuration and pure bounded correlation |
| services/ingestion-service/tests/test_security_evidence.py | Absent | Contract, scope, identity, counting and ambiguity checks |
| evals/security_evidence.py | Absent | Offline command using the same implementation; bounded file reads and JSON output |
| evals/security-evidence/cases.jsonl | Absent | Synthetic source settings and normalized input bundles only |
| evals/security-evidence/expected.jsonl | Absent | Evaluator-only expected counts, links and gaps |
| evals/tests/test_security_evidence.py | Absent | Fixture checks plus command errors and no-network assertion |
| evals/security-evidence/README.md | Absent | Runnable command, format, source trust assumptions and explicit limitations |
| evals/security-evidence/example-owner.json, example-gateway.jsonl, example-auth.jsonl | Absent | Executable example with owner configuration separate from events |
| docs/verification/security-evidence/ | Absent | Executed report and full local verification output |

Keep the existing scorer schemas, DB schema, tools, prompt, UI and archived results unchanged.
The existing ingestion/evals suites and Ruff targets already cover these Python locations.
No new framework, dependency, generic adapter registry or new test suite is needed.

## Verification checklist

- [x] Write the first failing check: one gateway record and one auth success in the
  same configured namespace produce one link citing both source-qualified IDs.
- [x] Add boundary checks before implementing parsing: extra source/namespace/header
  fields rejected; malformed IDs, naive times, bool status, oversized input and
  out-of-scope records rejected without echoing private values.
- [x] Implement parsing and correlation, then prove a same-string request ID in
  different namespaces does not link; no namespace also means no link.
- [x] Prove identical duplicates do not inflate counts; conflicting identities reject
  the bundle; multiple auth outcomes for one request remain an ambiguous group.
- [x] Prove HTTP 200 alone is not auth success; missing IDs do not trigger a time-based
  join; reversed timestamps do not establish or refute causal order.
- [x] Add suspicious distributed attempts, ordinary retries, shared-NAT activity,
  missing-auth, observed-success-with-unknown-impact and empty-input fixtures. Assert
  observations only, never attack/AI labels. Keep expected results outside runner inputs.
- [x] Run the command with networking forbidden and compare actual JSON to expected
  counts, citations and gaps. Confirm the runner never reads expected.jsonl.
- [x] Run the complete affected suites from their directories:

```bash
(cd services/ingestion-service && ../../.venv/bin/python -m pytest)
(cd evals && ../.venv/bin/python -m pytest)
make lint
.venv/bin/ruff format --check services/ingestion-service/app/security_evidence.py \
  services/ingestion-service/tests/test_security_evidence.py \
  evals/security_evidence.py evals/tests/test_security_evidence.py
git diff --check
```

- [x] Record actual output and self-review the diff. Commit/push identifies this checkpoint.

## Deliberate omissions

Production log adapters and persisted security ingestion follow this executable
contract. This slice does not inspect arbitrary existing log messages or connect to
customer infrastructure. UI and interview corrections remain separate work.

Plannotator tool was not exposed and `command -v plannotator` found no CLI. The owner
then explicitly said "just do it". No installation or paid execution occurred.
The implementation returns a JSON-compatible dict rather than adding an output-model
hierarchy. The public inspect_bundle boundary owns aggregate limits and validates the
owner configuration; parsing and correlation are internal typed stages.

[Verification evidence](../verification/security-evidence/README.md) records the report
and full local test output.
