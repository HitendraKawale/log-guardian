# Read-only investigation evidence

Issue #4 adds tools, not an agent or new HTTP endpoints. The scoring contract is unchanged. No tool executes commands, fetches a model-selected URL, reads arbitrary files, or loads evaluator labels.

## Interface

Construct `EvidenceTools` with an `InvestigationScope` and exactly one source:

- `records=` accepts validated replay log dictionaries and takes an immutable snapshot.
- `session=` accepts an owner-created SQLAlchemy async session. The caller owns its lifetime. Use a short session per tool operation; do not hold its transaction across later model calls.

The owner fixes `runbook_path` when constructing the tools. That path is not a tool argument. The default is the ingestion service's bundled `runbooks/operations.md`.

```python
from app.investigation_schemas import InvestigationScope
from app.investigation_tools import EvidenceTools

scope = InvestigationScope(
    services=["checkout", "inventory"],
    start="2026-01-01T10:00:00Z",
    end="2026-01-01T10:10:00Z",
)
# A replay case is selected and loaded by trusted application configuration.
tools = EvidenceTools(scope, records=case["logs"])
logs = await tools.query_logs(**scope.model_dump(), limit=50)
summary = await tools.summarize_logs(**scope.model_dump())
runbooks = await tools.search_runbooks(query="upstream timeout", limit=3)
```

`LogQuery`, `InvestigationScope`, and `RunbookQuery` provide the argument schemas for those three operations. Unknown arguments are rejected, including attempts to pass a filesystem path.

## Bounds and results

- Scope contains one to four unique services over more than zero and at most one hour. Inputs require timezone offsets and normalize to UTC. Both time endpoints are inclusive.
- Queries may narrow the authorized scope, never expand it.
- `query_logs` returns at most 50 records, newest event time first, with a stable source-specific ID tie-breaker. Text search is literal and case-sensitive, including Unicode; SQL wildcard characters have no special meaning.
- `summarize_logs` counts all matching records by service and level. It does not summarize only the first query page. Database counts use SQL aggregation.
- `search_runbooks` scores shared words in heading-sized sections and breaks ties by section ID. It returns at most three sections. This is a lexical baseline, not semantic retrieval.
- Every serialized result is at most 16,384 UTF-8 bytes, including metadata. Records that do not fit are omitted whole, not partially quoted. `truncated=true` reports row, byte, or retrieval limits. A narrower query may recover omitted records.
- Successful empty results have `error=null`. Invalid arguments, scope expansion, or unavailable sources instead return a named error with no raw SQL, filesystem exception, or credential-bearing input.

Each result includes a source, version fingerprint, evidence items, truncation status, and applicable time bounds. Replay IDs preserve fixture IDs; database IDs are `log:<id>`. Summary IDs include scope and content. Runbook IDs use stable section names such as `runbook:connection-pools`.

Log and summary versions fingerprint the redacted result content; they are not database transaction or whole-dataset versions. Runbook versions fingerprint the redacted document. The future runner must persist the returned snapshots and associate them with the run. These tools do not yet implement run persistence or a total cross-call evidence budget.

## Credentials and untrusted text

The shared redactor handles bearer tokens, common password/token/API-key assignments including quoted JSON fields, and URL user information. Redaction happens before result serialization and fingerprinting. Logs and runbooks remain untrusted data after redaction; injected instructions must never change tool permissions.

This is not general PII detection. Do not use arbitrary production logs on the assumption that all private information will be removed. The supported release scope remains authored and isolated sandbox data.

## Timestamp storage correction

SQLite drops timezone information from SQLAlchemy datetime values. Previously, an input such as `15:30+05:30` was stored as `15:30`, making a `10:00 UTC` investigation miss it.

`persist_log` now converts timestamps to UTC before storage. This is shared by REST and Kafka ingestion. Legacy naive inputs are interpreted as UTC, preserving their existing SQLite wall-clock value; investigation scope inputs still reject naive timestamps. The scorer receives the original request as before.

Existing SQLite rows may already have lost non-UTC offsets. This change cannot infer those offsets and does not rewrite historical rows. Re-ingest affected fixtures with known original timestamps or explicitly correct them before relying on historical time-window results.

## Verification

```bash
make test
make lint
cd services/ingestion-service
../../.venv/bin/python -m pytest tests/test_investigation_tools.py -v
```

The tool contract runs against replay and in-memory SQLite, including complete summary counts, literal search, scoped queries, byte limits, credential redaction, runbook version changes, and source failure. A REST ingestion test reproduces the timezone-storage bug through the real persistence function.

PostgreSQL uses its native `strpos` for literal text matching; SQLite uses `instr`. Live PostgreSQL and Docker image execution require separate runtime checks and are not proven by the SQLite suite. No provider SDK or paid calls are involved in this change.
