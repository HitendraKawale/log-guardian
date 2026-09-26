# Fresh-case evaluation authorization

Status: owner approved execution and the limits below in chat on 2026-09-23,
including local preparation commits. No push, PR, merge or further batch is authorized.
At authorization recording, no ledger had been claimed or provider request sent.

## Frozen inputs

- Candidate: 20e8e292e67b2cd7cc9968668fb63968446c56b17a52f6df06a89168fb905168.
- Candidate archive: evals/freezes/report-grounding-20e8e292e67b.tar.gz.
- Corpus freeze: af896fc98e7929be8507de15a14a1387c1ead48bd4b0b3ddb19c71cd14da2ab5.
- Corpus manifest: evals/freezes/fresh-report-grounding-af896fc98e79.json.
- Corpus archive: evals/freezes/fresh-report-grounding-af896fc98e79.tar.gz.
- cases.jsonl SHA-256: 74fcfffbd4e862ef56c45784da7813b1f22a03fff7610939b589d18d93f058ca.
- Twelve cases, fresh-01 through fresh-12, arranged in six pairs. Candidate only;
  no baseline arm or repeated samples are included in this proposal.

The corpus archive preserves all nine delivered authoring files, including scripts,
labels, rubric and provenance. Only cases.jsonl may feed runtime evidence. Labels,
pair objectives, rubric, provenance and authoring scripts remain evaluator-only.
The archive itself must not be exposed to the investigated model.

## Approved limits

- Model: gpt-4.1-mini-2025-04-14, standard service tier, official OpenAI endpoint.
- Execute each of the twelve cases once; at most six model requests per case,
  seventy-two requests total, zero SDK or transport retries.
- USD 0.10 per case and USD 2 total reservation ceilings. The native worker's
  stricter USD 0.025/run preflight budget remains in force.
- Preserve eight tool executions per case, 1024 output tokens per request,
  64 KiB aggregate evidence, 50 rows/16 KiB per query result and 120 seconds per run.
- Use a new exclusive shared-git ledger named fresh-report-grounding-2026-09-23.
- Reserve before each HTTP send, save response witnesses before tool dispatch,
  stop on ambiguous usage or transport failure, and never reopen a claimed batch.
- Preserve unsuccessful cases in the denominator. No repair attempts, retries or
  reuse of remaining allowances from this or previous batches.

## Required preparation

The existing live runner is fixed to the consumed ten-case batch. It cannot run
these cases unchanged. Prepare a new batch entry point/configuration and offline
checks for twelve-case limits, frozen candidate matching, input separation and
safe case storage. Do not change production prompt, tools, schema or budgets to
make preparation tests pass. Do not execute authoring scripts or overwrite freezes.

Pin the execution wrapper and dependency versions in a separate execution manifest
referencing both frozen digests above. Recheck official model pricing before live
execution; increase neither request nor monetary ceilings without new approval.
The source snapshot is immutable evidence, not a clean committed execution tree.
A local preparation commit and clean-worktree verification will also be needed;
no push, PR or merge is requested by this proposal.

## Assessment and limits

Inspect actual first-request bodies to verify which evidence and injections reached
the model. Count server-initial reads separately from model-proposed calls. Assess
report validity, claim support, uncertainty, source attribution, tool-policy attempts
and recommendation safety separately. Compare paired outcomes without inferring
internal reasoning or claiming enforcement recall when no violation is proposed.

Use a separate reviewer session for report assessment. Reveal frozen labels only
at evaluation time, not to the investigated model. Do not revise labels after seeing
outputs; record disagreements alongside the frozen labels.

The author declares exposure to repository instructions and path names. The candidate
author subsequently read scenario summaries in provenance.md after freezing the
candidate. These are separately model-authored synthetic cases, not strictly blinded
human-validated incidents. No candidate behavior on them is currently known. Twelve
paired cases without a baseline comparison cannot establish a general improvement
rate, calibrated accuracy or production readiness.

Any further candidate change requires a new candidate identity. Do not silently
replace this candidate after reading fresh-case outcomes or reuse these cases as
independent held-out evidence if they subsequently drive tuning.
