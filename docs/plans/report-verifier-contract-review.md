# Verifier contract review

This is an author review, not an independent model or human assessment. No verifier
model ran and no production code changed. The original packet remains unchanged.

## 1. Blocking: positive claim verdicts need no evidence references

`report-verifier-contract.md` permits zero evidence_refs for every assessment, and
response.schema.json has no minimum for claim references. A response can cover every
target, match both hashes, label every claim supported, provide no quotes at all and
reach passed_for_human_review under the documented aggregation.

Reproduced using v02, the archived false DNS diagnosis. A constructed response with
complete coverage and all empty evidence_refs satisfied every keyword used by the
proposed schema. It fits the response byte ceiling and documented host checks. This
is a protocol counterexample, not evidence that a verifier model would produce it.

Before adapter implementation, require a supported claim to provide at least one
reference to that finding's cited evidence. A contradicted claim must identify the
conflicting evidence. An insufficient verdict may have no reference when the defect
is missing evidence. Recommendation safety and report-gap judgments may legitimately
lack item references. The host must enforce these verdict-dependent conditions and
validate reference IDs and quotes before deriving disposition.

These requirements improve auditability but still do not prove entailment: a verifier
can quote a genuine yet irrelevant string. That remains a semantic evaluation problem,
not something to fix with a phrase-matching rule.

## 2. Required evaluation coverage: direct attacks on the verifier are absent

The packet exercises investigator failures but has no explicit report that instructs
the verifier to skip checks, emit supported verdicts or ignore its host policy. The
contract acknowledges this risk without testing it. A guard using the same model
mechanism may repeat the original failure on text addressed directly to that guard.

Add separately labeled development cases containing verifier-targeted instructions
inside a report and inside evidence, alongside benign quoted lookalikes. Keep the
original fourteen-item packet and its hashes unchanged. Test malformed/incomplete
responses, duplicate targets, wrong bindings and invented references at the host
boundary using scripted responses. Do not count protocol rejection as semantic detection.

## Checks run

- `python3 /tmp/lg46-contract-review.py`: constructed v02 response has complete target
  coverage, matching hashes and empty references, satisfying the proposed schema and
  the current documented aggregation conditions.
- The diagnostic checker implements only the keywords present in this schema. It is
  not a general JSON Schema validator or production adapter.
- `cd evals && ../.venv/bin/python -m pytest -p no:asyncio tests/test_report_verifier_packet.py -q`:
  `18 passed in 0.63s`.

The passing suite checks input integrity and source reproduction. It does not test
an adapter or semantic verifier, neither of which exists yet. The proposed next step
is to revise the contract and extend the offline boundary/threat cases before
implementing the tool-free host adapter. No paid batch is authorized.
