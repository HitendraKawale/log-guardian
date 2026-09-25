# Business-security investigation

Issue #48. This supersedes the primary-product direction in agent-security-product.md.
The owner clarified that Log Guardian should investigate attacks against businesses
and products, including suspected coordinated activity that might be AI-driven.
Commit verified milestones and push branches; no merging, paid calls or deployment.

## Goal

Investigate suspicious activity across a product's gateway, authentication and application logs.
Show the sequence of observed actions, affected services, supported impact and evidence gaps.
Prove the first workflow with bounded security fixtures and benign counterexamples, not model-generated claims of attack detection.

```text
[Gateway + auth logs] -> [Validated security evidence] -> [Bounded correlation]
                                                               |
[Human review] <-------- [Timeline + cited observations + gaps] <-+
```

Operational incident investigation remains part of the product. The generic Python
recorder is an optional source for systems that use agents. Keep its existing tests,
packaging and evidence. Do not delete the useful work or convert a tool-name finding
into an external-attack diagnosis.

## Findings from source inspection

- LogCreate and Log currently preserve service, level, message and timestamp, but
  no typed request ID, client address, account reference, HTTP status or auth outcome.
- InvestigationScope already bounds investigations to four services and one hour.
- ReplayLog forbids extra fields. Adding metadata to a fixture alone will not make
  it available through the investigator's current tools.
- The log scorer shares a duplicated wire contract across ingestion and AI service.
  Security metadata should not accidentally change the scoring model's inputs.
- The current detector selects severity/novelty/burst signals per service. It is not
  a cross-service credential-stuffing detector, and attack traffic can use INFO logs.
- Model reports have adopted hostile log text despite valid citations. Retain that
  evidence and do not treat the experimental verifier as a proven remedy.

## First investigation: suspected credential stuffing

A reviewer selects an application and time window after noticing failed logins.
The initial investigation should answer these narrower questions:

1. How many distinct authentication attempts and accounts are visible?
2. Which gateway requests can be linked to authentication outcomes?
3. Are failures concentrated on one account, spread across accounts, or spread across
   observed client addresses? State counts rather than equating IPs with people.
4. Was successful authentication observed within the suspicious activity?
5. What evidence would be needed to establish account compromise, data access or
   coordination, and which parts are missing?

Observed login success is not proof of compromise. Multiple IPs are not proof of a
coordinated actor. Similar timings or user agents are not proof of AI automation.
The product must not output an AI-swarm verdict merely because that is the user's hypothesis.

## Data and trust decisions

Use a separate typed security-evidence contract initially; leave the per-log scoring
API unchanged. Start with an offline import and correlation slice before designing
its persistent API. Do not infer structured fields by asking a model to parse prose.

Proposed minimum fields for gateway/auth events:

| Field | Meaning and constraint |
| --- | --- |
| evidence_id | Unique record identity within the imported source bundle |
| source_id | Owner-registered source; source identity is not supplied by a request body |
| event_time | Offset-aware source timestamp; retain clock uncertainty as an explicit gap |
| service | Owner-scoped application service |
| event_kind | gateway_request or authentication_result |
| request_id | Optional ID assigned or replaced by trusted infrastructure, not a claimed attacker ID |
| account_ref | Optional pseudonymous account identifier; no password, email or access token required |
| client_address | Optional address observed by the trusted ingress; not arbitrary X-Forwarded-For text |
| route | Normalized route without query strings or request bodies |
| http_status | Optional gateway status; never substitute it for an authentication result |
| auth_outcome | success, failure or unavailable for authentication evidence |

The owner specifies adapter/source configuration. The event must not declare itself
trusted. A trusted collector can faithfully record attacker-controlled values without
making those values authoritative. The import keeps provenance separate from content.

Only join requests on an owner-configured request-ID namespace whose generation and
propagation are known. Gateway and authentication sources may share that namespace;
independent applications must not. Evidence identity remains source-qualified.
Neither namespace nor source identity comes from event content. Missing IDs stay unlinked. Conflicting outcomes stay conflicts. Do not pair
rows on temporal proximity alone. Shared NAT, proxies, address rotation, delayed logs
and overlapping requests must not become invented actor identities.

Bound import size, records, services and time range. Return explicit rejected,
truncated or incomplete status; never label a partial dataset complete. Deduplicate
identical source/event identities and reject conflicting duplicates rather than
counting them twice or overwriting earlier evidence.

## Commit-sized delivery sequence

### 1. Deterministic evidence and correlation slice

Implementation decisions and review gate: [security evidence correlation](security-evidence-correlation.md).

- [x] Read source adapters and define the strict event and source-configuration models.
- [x] Add fail-first checks for invalid fields, duplicate/conflicting evidence, missing
  request IDs, forged forwarding headers, cross-source ID collisions and scope limits.
- [x] Implement bounded offline normalization and request/auth correlation. Output
  a timeline, source counts, linked outcomes, unresolved events and named gaps.
- [x] Build authored development cases for a suspicious distributed login pattern,
  ordinary retries, a shared-NAT traffic spike, missing auth logs, successful auth
  without compromise evidence, duplicate delivery and inconsistent clock/order data.
- [x] Keep expected judgments outside runtime inputs. Run with networking forbidden.
- [x] Prepare the verified slice for its milestone commit without advertising automated attack attribution.

The offline command and eight authored cases are implemented. Local verification
passed 705 offline checks plus six demo checks. See
[verification evidence](../verification/security-evidence/README.md).
Production adapters, persistent ingestion and the review UI remain unimplemented.

This milestone computes observations, not a confidence score. Threshold-based
selection and a model narrative are separate decisions requiring their own checks.

### 2. Persistent investigation workflow

- [ ] Choose and document an explicit gateway/auth adapter against actual source
  formats, with source-owned identity and proxy trust configuration.
- [ ] Add authenticated, bounded, idempotent ingestion and migrations for security
  evidence without changing existing scorer behavior or losing stored operational logs.
- [ ] Expose request-correlated evidence through scoped read-only investigation tools.
  Tool budgets, journal intent-before-dispatch and untrusted-source boundaries remain.
- [ ] Add a reviewable timeline and evidence gaps to the product UI. A user starts
  an investigation; incoming attack volume does not automatically spend model budget.
- [ ] Verify SQLite/PostgreSQL behavior, browser flows, privacy boundaries and failure
  handling. Any paid evaluation requires separate current authorization.

### 3. Correct the explanatory materials

- [ ] Replace the main preview story with a business under suspicious login activity:
  gateway evidence, linked auth results, investigation timeline, observed impact and gaps.
- [ ] Keep the agent-tool walkthrough as an optional integration example, not the hero.
- [ ] Correct the external interview document's pitch and planned-product answers;
  preserve historical facts about the recorder and model experiments.
- [ ] Rewrite the root README around log-based incident/security investigation and
  add a recorded animation of the working workflow, clearly separating fixtures from
  real customer incidents. Keep setup, threat model and evidence limits easy to find.

## File ownership

| Area | Current responsibility | Next responsibility |
| --- | --- | --- |
| New app security-evidence module and tests | None | Typed evidence, explicit source configuration and deterministic correlation |
| New offline fixture/runner files under evals | Investigator and agent-policy experiments | Bounded business-security rehearsal with evaluator-only expected results |
| Existing LogCreate/scorer schemas | Per-log scoring contract | Unchanged by the first offline slice |
| Later models/migration/routes/tools | Operational logs and investigations | Persistent security evidence integrated into investigation, not a disconnected agent-policy product |
| frontend preview and README | Investigator history plus optional-agent preview | Business-security explanation based on verified capabilities |

## What we carry forward

- Durable tool journals and unknown-outcome handling make the investigator auditable.
- Deterministic initial evidence fixed attack-delivery blind spots in bounded fixtures.
- Semantic failures demonstrate why untrusted logs need explicit attribution and why
  citations alone are insufficient. They remain open reliability constraints.
- The generic recorder can observe a business's own AI components when relevant to an
  incident. Its tool-name allowlist is not an external-traffic detector.

## Not in scope

No AI-attacker attribution classifier, autonomous blocking, account disabling,
automatic remediation, customer-data collection, real credential attacks, public
hosting, multi-tenancy, threat-intelligence subscription or new paid model batch.
Do not reuse consumed held-out data as independent validation after tuning on it.
A convincing synthetic demo is not evidence of real-world detection accuracy.
