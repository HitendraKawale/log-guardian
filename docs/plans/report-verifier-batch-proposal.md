# Verifier batch proposal

Status: UNAPPROVED. The owner authorized offline runner and proposal preparation only.
No model calls, spending, live transport implementation, commits, pushes or production
integration are authorized. Approval must explicitly name the model and limits below.
All earlier paid allowances remain closed and cannot fund this experiment.

## Question and candidate

Can a tool-free verifier reject the packet's labeled semantic defects without
rejecting its acceptable controls? This is a development experiment, not an accuracy
benchmark or production-acceptance test.

Proposed candidate: the v2 contract, current host policy and prepared inputs/schema.
The provider-neutral preparation is preserved at:
`evals/results/report-verifier-offline-runner-verified/prepared/`.

Preparation manifest SHA-256:
`3bc448eadf44ab2e5e586509e092cefaf5c6e5cf13146c3f20e97efc31df3b60`.

The manifest pins every prepared request, eighteen inputs, source files and local
Python/Pydantic versions. Each eligible request contains only the host policy,
its exact input object and the response schema. Expected labels, source mappings,
scripted responses and prior judgments must never enter the model request.
The largest prepared artifact is 12,334 bytes. Provider-specific request serialization
and schema support have not been implemented or verified.

## Proposed limits

| Setting | Proposal |
| --- | --- |
| Provider/model | Official OpenAI, gpt-4.1-mini-2025-04-14, standard tier |
| Endpoint | https://api.openai.com/v1/chat/completions, subject to official compatibility verification before preparation of a live adapter |
| Cases | Seventeen eligible reports, one request each; v13 fails locally and must not be sent |
| Request ceiling | Seventeen total, including failed or ambiguous sends; no repeats or repairs |
| Output ceiling | 4096 tokens per request; extracted verifier JSON still capped at 16 KiB |
| Deadline | 60 seconds per request, 20 minutes for the batch |
| Spend ceilings | USD 0.10 per report and USD 2 total, reserved before sending |
| Wire limits | At most 128 KiB serialized request and 128 KiB HTTP response capture; oversize means failure, never silent truncation into an accepted response |
| Retries | Zero SDK, transport or application retries |
| Tools | None; no retrieval, actions, repair or fallback acceptance |
| Proposed new ledger | report-verifier-v2-pilot-01 in the shared git directory; never reuse an existing claimed directory |

This uses the same model revision that generated the investigator reports. That
reduces model-comparison scope but may retain correlated errors. It is not an
independent judge. A different model or comparison arm requires a revised proposal.

Pricing is a dated planning assumption, not a fresh lookup: the official-document
check preserved in fresh-report-grounding-pricing.md on 2026-09-23 recorded USD 0.40
input and USD 1.60 output per million tokens. Ignore cache discounts when reserving.
Using 128 KiB wire bytes plus 4096 overhead tokens as the input reservation and 4096
output tokens gives USD 0.0606208 per request, USD 1.0305536 for seventeen requests
at those dated prices. These are conservative reservations, not invoices or a price
guarantee. Refresh official pricing before a live batch; do not raise ceilings silently.

## Blocking prerequisites after any approval

The current runner has no live mode and cannot execute this proposal. A separately
approved transport-preparation step must:

- Verify official endpoint/model/schema support and current prices. Preserve a
  provider-neutral-to-wire mapping that adds no labels and removes no evidence.
- Implement zero retries, no redirects/proxy fallback, deadlines, bounded response
  capture and strict model/tier/token-usage checks. No request for the local-invalid case.
- Claim the new shared ledger exclusively and reserve before every HTTP send.
  Preserve raw request/response witnesses and unsuccessful cases. Stop on ambiguous
  transport, usage or accounting failures; do not reuse unused allowance afterward.
- Mark later unattempted cases separately from malformed, failed or timed-out cases.
  The offline replay currently calls missing files verifier_error because it has no
  transport metadata and cannot infer whether they were attempted.
- Freeze and review the adapter, dependencies and final wire requests. Obtain separate
  permission for any preparation commit and require a clean execution revision.
  The current uncommitted worktree is not an approved live-execution revision.

An approval of the proposed limits alone does not establish that these prerequisites
are complete or authorize production integration. Do not begin sending while they
remain unmet.

## Scoring and stop conditions

The packet has eight expected acceptable reports, nine semantic negatives and one
local-invalid control. Count all eighteen cases, but keep the local control out of
semantic detection denominators. Evaluate once against frozen labels; keep disputes
in a separate adjudication file rather than revising labels after seeing responses.

Report acceptable-report rejections with substantive/error counts, known-bad passes,
required-defect targets rejected or missed, exact verdict disagreements, malformed
responses, timeouts, unattempted cases, tokens, cost and latency. A wrong-target
rejection is not detection of the labeled defect. An error is not successful semantic
detection. The runner recomputes stored verdicts from saved response bytes before scoring.

No result authorizes a production gate. A missed unsafe recommendation or adopted
verifier-targeting instruction requires investigation before another candidate is
proposed. Even zero misses on this small, tuned packet would require new independently
reviewed material and measurement of false-rejection burden before production use.

## Offline evidence only

The verified CLI exercise produced eight scripted passes, nine scripted semantic
rejections and one local block. Its responses were deliberately generated from labels.
These counts validate runner accounting, not model behavior or injection resistance.
The runner tests also exercise missing, malformed, oversized and wrongly bound responses,
wrong positive verdicts, mismatched defect verdicts, tampering and output refusal.
