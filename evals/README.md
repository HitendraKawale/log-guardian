# Incident evaluation corpus

Version `1.0.0` contains eight development cases, sixteen held-out cases, and 169 log observations. It supports investigation evaluation, not per-log anomaly classification.

These are AI-assisted, explicitly authored engineering fixtures. They are not customer incidents, operator-labeled production data, BGL excerpts, or results from the live sandbox. Expected diagnoses were authored separately from observations, not inferred from the old anomaly scorer. The [first live development smoke evaluation](results/2026-09-13-baseline-smoke/README.md) contains four A/B requests on two cases. Both systems failed the required abstention; no held-out evaluation has run.

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

## Run the A/B baselines

The runner uses the ingestion service's tools and report schema. Install the shared environment with `make install`; unlike the validator, the runner requires the service dependencies, including pinned `openai==2.11.0`.

Inspect a development case without a provider key or network request:

```bash
.venv/bin/python evals/run.py --system B --case dev-01 \
  --model gpt-4.1-mini-2025-04-14 --max-cost-usd 0.10 --dry-run
```

A uses one log query. B always uses a log query, a full-scope summary, and runbook retrieval using the first 512 characters of the sanitized question. Each then makes exactly one SDK request. Neither is an adaptive agent. The model receives evidence as tool messages, not system instructions.

Live execution requires separate owner approval, `OPENAI_API_KEY`, a clean committed worktree, `--allow-live`, and an explicit per-run allowance. `--model` can also come from `LLM_MODEL`; there is no model default. The only currently supported snapshot is `gpt-4.1-mini-2025-04-14`. Missing credentials never produce a fabricated report. The CLI uses the official API endpoint, not an environment-supplied proxy URL.

After approval, replace `--dry-run` with `--allow-live`. Add `--output path/to/new-run.json` to preserve an artifact; its parent directory must exist. Existing paths are refused before any provider request. Without `--output`, the command emits JSON on stdout. Exit codes are 0 for a completed report or dry run, 1 for a recorded run failure, and 2 for invalid configuration or an unavailable output path. An interrupted process can leave an empty reserved output file; do not present it as a completed run. Save live artifacts outside the worktree until the evaluation batch finishes: untracked output files inside the repo would make the next invocation fail its clean-worktree check.

The CLI selects only development case IDs from its fixed corpus location. It has no fixture-path option and does not open labels or held-out evidence. A run artifact records authored incident provenance separately from live, scripted, or dry-run model execution.

### Reports, failures, and accounting

Reports contain observations, a supported likely cause or an inconclusive outcome, alternatives, missing evidence, and suggested read-only checks. Every finding requires citations from successful evidence results. A likely cause cannot cite only a runbook or an empty summary. Citation validation establishes membership, not whether a claim follows from its evidence; semantic review remains required.

Invalid reports, refusals, truncated model outputs, model mismatches, and provider errors remain failures. Raw rejected output and provider error bodies are not exported. Returned usage is retained when report validation fails. Missing usage or an ambiguous failed request produces null usage/cost, not zero. SDK retries are disabled. The baseline does not attempt report repair, keeping the comparison to one request.

The runner limits execution to 120 seconds, evidence to 64 KiB, and requested output to 1,024 tokens. The tool-level limits still apply. Before a provider request, it reserves an estimate using serialized input bytes plus 4,096 protocol-overhead tokens and the output ceiling, without a cache discount. This deliberately conservative byte-based estimate is not a billing guarantee, account-wide ledger, or permission for public paid execution. Reported cost above the allowance is flagged after the response; that cannot undo a charge already incurred.

Price estimates use the dated table in `app/investigation_agent.py`. The official model page checked on 2026-09-13 lists $0.40 input, $0.10 cached input, and $1.60 output per million tokens. Returned cached counts receive the discount. If the provider omits cache details, the estimate assumes no discount. Recheck prices and model availability before live evaluation.

Artifacts include the model requested and returned, SDK version, prompt/schema hash, code revision and implementation digest, case and corpus hashes, tool arguments and redacted evidence snapshots, latency, usage, limits, and the dated price table. Dry runs contain no report. Scripted HTTP tests exercise the real SDK but are not live quality or cost measurements. The [recorded development smoke results](results/2026-09-13-baseline-smoke/README.md) preserve all four original reports, including two semantic failures. They are not a complete scorecard or proof of production reliability.

### Offline correction candidate

After the first smoke evaluation, lexical retrieval now ignores common question words and includes stable section IDs in matching. The recorded question "What caused the search timeouts?" now retrieves `timeouts` first; stop-word-only queries return no matches. Retrieval remains lexical, with no stemming, embeddings, or case-specific routing.

The shared prompt now distinguishes unavailable telemetry from application failures, requires evidence for request-path dependencies, and warns against health-probe generalizations. These are general instructions, not a rule that forces an outcome based on a case ID or log keyword. Tests verify retrieval and that the SDK receives the policy; they do not prove the model follows it.

The original four reports and their hashes remain unchanged. The prompt hash and implementation digest identify this new candidate. Prompt and retrieval changed together, so a future comparison cannot attribute improvement to either change alone. The [second live smoke batch](results/2026-09-13-baseline-smoke-v2/README.md) evaluated this candidate. Both systems again failed to abstain on dev-06 despite improved targeted retrieval. Step 6 remains open. Both batches are preserved, with eight requests costing an estimated $0.00768160 in total. Both original request allowances are exhausted.

The [offline diagnosis](../docs/baseline-abstention-diagnosis.md) found that the schema emitted outcome before observations and missing evidence. A new candidate changes only field order; live improvement is unverified. The owner approved a separate four-request, $0.10 trial on the same model and development cases. This is not a general authorization to run the CLI.

Sources: [SDK 2.11.0 configuration](https://github.com/openai/openai-python/blob/v2.11.0/README.md), [SDK API](https://github.com/openai/openai-python/blob/v2.11.0/api.md), [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), and [model snapshots and pricing](https://developers.openai.com/api/docs/models/gpt-4.1-mini).

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
