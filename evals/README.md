# Incident evaluation corpus

Version `1.0.0` contains eight development cases, sixteen held-out cases, and 169 log observations. It supports investigation evaluation, not per-log anomaly classification.

These are AI-assisted, explicitly authored engineering fixtures. They are not customer incidents, operator-labeled production data, BGL excerpts, or results from the live sandbox. Expected diagnoses were authored separately from observations, not inferred from the old anomaly scorer. No model has been evaluated against this corpus yet.

## Run the checks

Python 3.11 is sufficient for the validator. It uses only the standard library, makes no network requests, and changes no files.

```bash
python3 evals/validate.py
python3 evals/validate.py --root evals --json

# Existing project environment, including tests and lint
make validate-corpus
make test-evals
make test
make lint
```

Success exits 0. Invalid data or missing files exit 1 with an error on stderr. Invalid CLI arguments exit 2. `--json` returns counts, dataset version, and SHA-256 hashes of all three input files without a prose prefix. Repeated runs on unchanged bytes return identical hashes.

CI runs the evaluation tests as their own matrix entry. The tests validate the checked-in corpus and mutate small independent examples to exercise rejection behavior. They do not call a model or consume API credits.

## Files and separation

| File | Consumer | Contents |
| --- | --- | --- |
| `cases/dev.jsonl` | Development runner and tools | Eight evidence bundles |
| `cases/test.jsonl` | Held-out evaluation runner and tools | Sixteen evidence bundles |
| `labels.jsonl` | Offline evaluator only | Expected outcomes, explanations, acceptable alternatives, evidence references, forbidden claims, missing evidence, variant IDs, and coverage tags |
| `validate.py` | Local checks and CI | Evidence loading and corpus consistency checks |

Each evidence line is one JSON object:

```json
{
  "schema_version": 1,
  "dataset_version": "1.0.0",
  "case_id": "dev-01",
  "provenance": "authored",
  "question": "Why did checkout begin returning 504 responses?",
  "scope": {
    "services": ["checkout", "inventory"],
    "start": "2026-01-01T10:00:00+00:00",
    "end": "2026-01-01T10:10:00+00:00"
  },
  "logs": [
    {
      "evidence_id": "dev-01:01",
      "service": "checkout",
      "level": "INFO",
      "message": "request r101 started; dependency=inventory; deadline_ms=5000",
      "timestamp": "2026-01-01T10:00:05+00:00"
    }
  ]
}
```

The example above shows the shape, not the complete case. An observation uses the existing four log fields plus a stable evidence ID. Do not attach scores, expected diagnoses, scenario names, or grader labels to it.

`load_cases(path)` validates evidence only and does not open any labels file. `validate_corpus(root)` is the offline check that joins labels to evidence. Neither function is a public path-selection API. Future tool callers must select fixture paths from server-owned configuration, not user or model input.

The current service Dockerfiles do not copy `evals/`. Keep labels out of runtime images, retrieval indexes, prompts, tool results, and public demo exports. File separation alone is not a security sandbox: any process granted unrestricted filesystem access could still read the labels. The future agent must not have such a tool.

## Coverage

| Family | Development | Held-out |
| --- | ---: | ---: |
| Upstream latency | 1 | 4 |
| Connection exhaustion | 2 | 3 |
| Credential/configuration failures | 3 | 4 |
| Benign or ambiguous errors | 2 | 5 |

Twenty cases have a supported explanation. Four require an inconclusive result because important causal evidence is absent or unreliable. A supported explanation may be a benign business failure rather than an infrastructure outage. Some establish which deadline was exceeded without establishing the internal reason for an upstream delay.

The corpus includes healthy probes alongside failing requests, credential/configuration evidence, independent simultaneous failures, uncertain event ordering, missing upstream observations, and attacker-controlled instructions inside log text. One held-out case contains 56 observations so a 50-row query must report truncation. These cases do not substitute for actual timeout, provider failure, or capability-enforcement tests.

Scope intervals are inclusive at both endpoints and at most one hour long. Timestamps must include an offset. The validator compares aware datetimes, so equivalent UTC and non-UTC values share the same interval. Fixed timestamps describe independent replay namespaces, not simultaneous incidents in one live environment.

## Labels and grading

The label's `variant_id` identifies a causal scenario, not just its service names. Its `expected_cause` states the most specific explanation the observations justify. `supporting_evidence_ids` identify the observations a reviewer should consult. `acceptable_alternatives` is an explicit allowance for additional explanations, not permission to accept arbitrary plausible stories; it is currently empty for all cases.

For `inconclusive` cases, `expected_cause` is null and `required_missing_evidence` names what is needed. The cited observations support abstention, not a hidden root-cause answer. `forbidden_claims` records consequential conclusions or actions the evidence does not support.

Future graders should judge semantic equivalence, not exact string matches. Review each material claim against the cited observations. A correct citation ID does not prove entailment. Keep unsupported diagnoses, unavailable tools, and other failures in the denominator. Report abstention separately from diagnosis accuracy.

## Versions and leakage limits

- `schema_version` changes when the evidence contract changes. This validator accepts version 1.
- `dataset_version` changes when case content, split membership, or grading labels change. All evidence and labels must agree on it.
- Stable case/evidence IDs survive unchanged content. Retain old dataset artifacts or their Git revision when publishing results, and record the three content hashes printed by the validator.
- Split by incident variant, not log row. The validator rejects duplicate case/evidence IDs, repeated variant IDs, and identical observation sets after normalization of service names, numeric values, case, whitespace, and ordering.
- That fingerprint catches cosmetic copies, not semantic paraphrases. Human review must catch repeated mechanisms disguised by rewriting. It can also reject numeric-only distinctions intentionally; explain such cases before weakening the check.
- Unknown fields are rejected at every evidence-object level, preventing structural label leakage. This does not detect an answer pasted into an otherwise valid message or question. Review content as well as schema.
- Tune only on development cases. Freeze the prompt/model candidate before held-out evaluation. If held-out failures drive another prompt revision, create a new held-out set before claiming an independent comparison.

The same assistant authored both splits. This is not an independently collected blind benchmark. A small controlled corpus can test system behavior and compare approaches, but cannot establish production reliability. Most cases are short enough for a one-shot baseline to see all evidence; do not assume adaptive retrieval will win. Live-origin cases and independent review remain planned follow-up work.
