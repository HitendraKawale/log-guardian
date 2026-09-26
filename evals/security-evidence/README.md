# Offline security evidence correlation

This is the first business-security investigation milestone, not an attack classifier.
It links normalized gateway requests to authentication results using owner-configured
request-ID namespaces. It returns observations, evidence references and gaps without
calling a model, accessing a network or writing files.

## Run the example

From the repository root, with the shared development environment installed:

```bash
.venv/bin/python evals/security_evidence.py \
  --config evals/security-evidence/example-owner.json \
  --source gateway=evals/security-evidence/example-gateway.jsonl \
  --source authentication=evals/security-evidence/example-auth.jsonl
```

The authored example has three gateway requests from three documentation-range
addresses, three account references and three linked auth results: two failures and
one success. Gateway records deliberately use HTTP 200 even for failed authentication.
This proves that HTTP status is not used to manufacture authentication success.

The report is JSON on stdout. Exit 0 means the bounded input was accepted and analyzed,
not that traffic is safe. Errors go to stderr with exit 2 and no partial report.
`--help` describes the command. Repeat `--source ID=PATH` once per configured source;
use an empty file if that source has no supplied events. No implicit files or labels
are loaded. No provider key is needed.

## Source ownership and input contract

`example-owner.json` defines the allowed services and time window, each source's ID,
event kind and service, and optional request-ID namespace. These values belong to
the owner. Event bodies containing source_id, service, request_namespace, headers,
credentials or arbitrary message fields are rejected, not used as configuration.

Only assign a shared namespace if trusted infrastructure replaces or generates unique
request IDs and propagates them between those sources. Leave it null when that is not
known. Raw client-supplied request IDs are not safe correlation keys. The import does
not verify that the configured trust assumptions hold in a real deployment.

| Event fields | Required | Optional |
| --- | --- | --- |
| Both kinds | evidence_id, event_time | request_id |
| gateway_request | route | client_address, http_status |
| authentication_result | auth_outcome | account_ref |

Use aware ISO timestamps. The parser normalizes them to UTC. IDs are bounded ASCII
tokens, not emails or free text. Auth outcome is success, failure or unavailable.
HTTP status is a strict integer from 100 through 599. Routes are normalized path
names or templates, with no query, fragment, whitespace or percent encoding.
Client addresses must be IP literals and come from the configured ingress observation,
not arbitrary forwarding headers. Account references should be pseudonymous.

These are normalized fixtures, not a parser for nginx, Cloudflare, a SIEM export or
arbitrary application output. A production adapter and its source-trust checks remain
unimplemented. Existing LogCreate, scoring, persistence and investigator tools are unchanged.

## How to read the output

- `timeline` sorts unique evidence by normalized source time, then source/event ID.
  Source time does not establish causal order; access logs may timestamp completion.
- `links` contains exactly one gateway record and one auth record sharing a configured
  namespace and request ID. Both records are cited with `[source_id, evidence_id]`.
- `ambiguous_groups` retains all evidence when multiple gateway or multiple auth
  records reuse one request key. No arbitrary winner or confirmed link is chosen.
- `unlinked` includes every unique record outside confirmed pairs, including ambiguity.
- `sources` counts unique records, distinct observed gateway addresses, distinct
  per-auth-source account references and recorded auth outcomes. These are not people,
  independent actors or inferred attack attempts. Zero known account references can
  mean missing identifiers, not zero accounts.
- `input_records` includes repeated delivery; `duplicate_records` reports identical
  canonical evidence removed from the timeline. Conflicting content under the same
  source/event identity rejects the bundle rather than overwriting it.
- `gaps` names empty sources, missing counterparts/IDs, ambiguous IDs and unavailable
  auth outcomes. `limitations` always states unknown completeness, unverified clock
  alignment, unestablished impact and unestablished actor/AI attribution.
- `collection_complete` is always null. No file content can prove all events were
  captured. Empty input means no supplied evidence, not no attack.

A linked success proves only that the imported auth source recorded success. It does
not prove credential ownership, account compromise, data access or AI-driven activity.
A linked `unavailable` result still has an unknown authentication outcome.

## Limits and privacy

The bundle is limited to four configured sources, four scoped services, a positive
window of at most one hour, 1 MiB total event bytes, 1,000 input records before
deduplication and 16 KiB per line. Owner configuration is capped at 16 KiB by the CLI.
Limit violations and out-of-scope records reject the whole bundle; no silent truncation.
Duplicate JSON keys, floating-point numbers, malformed UTF-8 and unknown fields fail
validation. Validation errors do not echo rejected event bodies.

The first implementation is in-memory. It does not resume, watch files, fetch remote
logs or provide a persistent API. Files must be regular local files. No third-party
runtime dependency was added; Pydantic is already part of ingestion/evals.

Addresses, account references, routes and request IDs appear in the output and may be
sensitive. There is no automatic anonymization or retention service. Normalize routes
and pseudonymize accounts before import; token validation cannot prove that a value is
non-sensitive. Protect the input files and any redirected report as security evidence.

## Development checks

`cases.jsonl` contains eight assistant-authored synthetic inputs: suspicious distributed
activity, ordinary retries, shared-NAT successes, missing auth logs, success with unknown
impact, duplicate delivery, request-ID reuse and empty input. The names describe the
fixture author's scenario, not a classifier output. Auth timestamps precede gateway
completion timestamps to guard against assumed clock/causal order.

`expected.jsonl` contains hand-counted evaluator-only expectations. The test reads it;
the runtime command does not. These are development cases, not independent, blinded
or customer-validated examples. No attack-recall or false-positive-rate claim follows.

```bash
(cd services/ingestion-service && ../../.venv/bin/python -m pytest tests/test_security_evidence.py)
(cd evals && ../.venv/bin/python -m pytest tests/test_security_evidence.py)
```

Tests deny Python socket creation while invoking the offline command, guard against
runtime expectation-file reads, and check rejected-input privacy. This is a test
assertion about this execution path, not an OS network sandbox.
