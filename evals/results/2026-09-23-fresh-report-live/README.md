# Fresh-case live batch: semantic review pending

The approved one-shot batch completed on 2026-09-23 using
gpt-4.1-mini-2025-04-14 on standard service tier. Execution revision:
c6e75f05ec07fbea872f4af6264f0d726e9759ab.

- Production candidate: 20e8e292e67b2cd7cc9968668fb63968446c56b17a52f6df06a89168fb905168.
- Corpus freeze: af896fc98e7929be8507de15a14a1387c1ead48bd4b0b3ddb19c71cd14da2ab5.
- Execution digest: c58186843f75aa17abd1c03f177ebdc58ee3bb2718bb848e55bdae374f7cf763.

## Observed transport and capture results

All twelve cases completed with twelve successful provider responses, one per case.
All twelve reports passed schema/citation checks. That is not semantic validation.
All 106 scoped fixture rows were present in the first requests, without result
truncation. All six injected rows were delivered. No inventory canary was exposed.

The model proposed zero follow-up tools. The twelve server-initial reads produced
twelve committed intent events and twelve linked completions, with no unresolved
requests. Every exported journal and terminal status matched a read-only query of
its closed SQLite database. No scope-violating proposal or denied call occurred;
therefore this batch does not measure scope-enforcement recall.

Reported usage: 24,758 input tokens, 4,365 output tokens, zero cached input tokens.
Estimated cost: USD 0.0168872, equal to the noncached usage estimate. Conservative
reservations: USD 0.09001880. These are not billing receipts. There were no retries,
transport ambiguity or missing usage. The batch is closed despite unused ceilings.

## Separation and provenance

The fresh author declared exposure to repository instructions and path names.
The candidate author read scenario summaries in provenance after freezing the
candidate. These are separately model-authored synthetic cases, not strictly
blinded human-validated incidents. No baseline arm or repeat samples were run.
Neither improvement rates nor general model accuracy follow from this batch.

Only cases.jsonl supplied runtime fixture evidence. Author labels, pair objectives,
rubric and provenance were excluded from the execution snapshot and requests.
Offline input-separation tests prevented opening those files during the scripted
worker rehearsal. After live completion, the capture analysis read pair IDs only
to check injection exposure; no diagnostic grading was performed by that script.

`capture-analysis.json` contains counts, first-request coverage, proposal/journal
comparison and usage. It intentionally contains no semantic success verdict.
A separate model review against actual delivered evidence and then frozen author
labels remains pending. Do not call twelve accepted reports twelve correct reports,
or six delivered attacks six successful defenses.

## Preserved evidence

`original-files.json` hashes all original ledger files. JSON and source snapshots
are byte-identical. The closed SQLite databases are compressed losslessly with
fixed gzip timestamps. Request headers were never saved; response witnesses contain
decoded JSON before SDK dispatch, not raw TLS captures. The archive and decompressed
databases were checked for the current API credential without printing it.

Verify with `shasum -a 256 -c SHA256SUMS`. This later README is excluded from that list.
`capture-analysis-driver.py.txt` preserves the executed offline analysis procedure.
The shared ledger is fresh-report-grounding-2026-09-23 and must not be reopened.
Both preceding paid ledgers, the source candidate and the corpus remain unchanged.

Preflight passed 552 offline tests plus six demo tests and lint. Local preparation
commits were authorized; nothing was pushed. This live archive is uncommitted.
No runtime code was changed after the freeze or in response to these results.
