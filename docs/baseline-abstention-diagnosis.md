# Abstention diagnosis and schema-order experiment

The client can carry an inconclusive report without changing it to supported. The remaining live failure is an unsupported generated causal claim that passes membership-only citation validation. Why the model selects that claim is not yet established.

## Evidence gathered offline

`evals/tests/test_baseline_diagnosis.py` reconstructs A and B on the actual dev-06 evidence through the real OpenAI SDK and an HTTPX mock transport. No provider request is sent.

Before the candidate edit, both diagnostic cases passed with the second batch's prompt/schema hash and exactly the archived tool-result payloads. The reconstructed SDK request contained the missing-telemetry policy. Its schema allowed both outcomes and a null cause. A scripted inconclusive response with observed timeout citations survived parsing, redaction, coherence validation, and citation validation unchanged.

This rules out a forced-supported local schema or a local conversion of inconclusive to supported on this path. It does not prove that a live model follows the policy. Historical raw HTTP requests were not archived, so this is a reconstruction from the preserved code/evidence, not an attestation of remote processing.

## New hypothesis: conclusion-first generation

The evaluated schema declares its fields in this order:

```text
outcome -> observations -> likely_cause -> alternatives -> missing_evidence -> suggested_checks
```

The [official Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs), checked on 2026-09-13, states:

> When using Structured Outputs, outputs will be produced in the same order as the ordering of keys in the schema.

Context7 did not return this specific detail; it was checked directly in the official guide.

The schema therefore requests a supported/inconclusive decision before the report's evidence and gaps. Early commitment is a plausible contributor to the later unsupported cause. The ordering behavior is documented; its causal effect on this failure is a hypothesis, not a proven diagnosis.

## One-variable candidate

Only reorder the existing `InvestigationReport` declarations:

```text
observations -> missing_evidence -> alternatives -> likely_cause -> outcome -> suggested_checks
```

No fields, types, constraints, validators, prompt text, model, SDK pin, question, evidence, or retrieval behavior change. This is visible report ordering, not a request for hidden reasoning. An AST comparison verified unchanged field definitions and validators, and a Git comparison verified unchanged prompt/runner/retrieval/corpus files relative to `0a97c3f`.

The boundary tests first failed on the old key order, then passed on the candidate order. They still verify unchanged evidence payloads and successful transport of a scripted inconclusive response. Both original live batches continue to pass their archive hash checks.

The combined prompt/schema fingerprint changes even though the prompt text does not:

- Evaluated second batch: `7490913eb179976232ddc28f8cbe8e60eb262f7a847fda46cf972fb27131f2cb`
- Candidate: `cb18775883d13c3740332ed3e98b1b0f7358b4a494967a2e360cafd77e2f66c6`

## Verification and remaining gate

Fresh `make test`: 187 passed. `make lint`: `All checks passed!`, `68 files already formatted`. These are offline checks, not evidence of improved live abstention.

A future trial should repeat A/B on the same supported and inconclusive development cases, at the same model snapshot, temperature, and request limits. Preserve every result, including failures, and compare required abstention as well as the supported case. Do not attribute any result to a new prompt or retriever: neither changes in this candidate. Two cases remain insufficient for general quality claims.

At diagnosis time, the candidate and second-batch archive were uncommitted and both paid authorizations were exhausted. The owner subsequently approved committing/pushing this update and a separate four-request trial on `gpt-4.1-mini-2025-04-14`, with a fresh $0.10 total allowance and $0.025 per invocation. Only A/B on dev-01 and dev-06 are in scope; no retries or held-out cases. The [third live batch](../evals/results/2026-09-13-baseline-smoke-v3/README.md) subsequently supplied the supported and inconclusive examples for step 6. A abstained without the unsupported collector dependency; B moved that dependency into alternatives despite an inconclusive label. The change coincided with an improvement on one selected case, not a proven causal effect or general reliability. This diagnostic's scripted reply is not the live example. Fresh post-archive verification passed 188 tests and lint. All four requests are consumed; estimated cost was $0.00409200.
