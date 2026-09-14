# Evaluation method and scorecard

Log Guardian's investigation systems are compared on an authored incident corpus with per-case rubrics. Every live run is preserved byte-for-byte with provenance; failures stay in the denominator. This document is the complete record.

## Method

- **Corpus**: 8 development + 16 held-out authored cases, 169 observations, separate evaluator labels (`evals/labels.jsonl`) that never reach runtime. AI-assisted fixtures, not production incidents or a blind benchmark. One additional live-origin bundle exists from the demo sandbox (`demo/bundles/`).
- **Systems**: A (one scoped log query), B (fixed log + summary + runbook retrieval), C (adaptive tool selection, ≤6 model requests, ≤8 tool executions, 120s, 64KiB evidence).
- **Model**: `gpt-4.1-mini-2025-04-14`, SDK 2.11.0, temperature 0, structured outputs, no retries. Ambiguous billing stops a run with null usage, never zero.
- **Grading**: reports validate against a strict schema plus citation-membership checks; semantic "core review" judges the diagnosis against the rubric and forbidden claims. Reviewer is the project's coding assistant, not independent or blind. Citation membership does not prove semantic support.
- **Reproduction**: `evals/run.py --system A|B|C --case <id> [--held-out] --model gpt-4.1-mini-2025-04-14 --max-cost-usd 0.025 --dry-run|--allow-live`. Each artifact records code revision, implementation/corpus/case hashes, prompt/schema hash, usage, dated pricing, timings and limits.

## Complete scorecard (all live batches)

| Batch | Revision | Runs | Requests | Est. cost | Key result |
| --- | --- | ---: | ---: | ---: | --- |
| [Smoke 1](../evals/results/2026-09-13-baseline-smoke/) | `e4edf8b` | 4 | 4 | $0.00366960 | Both A/B failed required abstention on dev-06 |
| [Smoke 2](../evals/results/2026-09-13-baseline-smoke-v2/) | `0a97c3f` | 4 | 4 | $0.00401200 | Prompt+retrieval fix did not restore abstention |
| [Smoke 3](../evals/results/2026-09-13-baseline-smoke-v3/) | `8edf09e` | 4 | 4 | $0.00409200 | Schema-order change; A abstained correctly |
| [Dev A/B/C](../evals/results/2026-09-14-dev-abc/) | `ad7f95f` | 24 | 46 | $0.03470640 | A 7/8, B 7/8, C 4/8 core passes |
| [C rerun](../evals/results/2026-09-14-dev-c2/) | `998ed13` | 8 | 20 | $0.01367280 | C 5/8 after tool-guidance fix |
| [Held-out](../evals/results/2026-09-14-heldout/) | `7f3889b` | 48 | 74 | $0.06788320 | A 12/16, B 13/16, C 11/16 |
| **Total** | | **92** | **152** | **$0.12803600** | |

Held-out detail (the only evaluation of that split):

| System | Core pass | Required abstentions | False abstentions | Execution failures | Cost | Mean latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 12/16 | 0/3 | 1 | 1 | $0.01514360 | ~3.5s/run |
| B | 13/16 | 1/3 | 1 | 0 | $0.02351560 | ~4s/run |
| C | 11/16 | 1/3 | 1 | 3 | $0.02922400 | ~8s/run (2-5 requests) |

**The headline finding is negative**: adaptive evidence collection (C) did not beat fixed retrieval (B) on this corpus. B leads at ~80% of C's cost. Most cases are small enough for one-shot retrieval to see all evidence, which the plan anticipated.

## Failure analyses

1. **Invented causal dependency (dev-06, three batches).** Given caller timeouts and a collector warning that log export was unavailable, A and B repeatedly asserted that the missing telemetry *caused* the timeouts, inventing a request-path dependency between services that only share a scope. A prompt policy explicitly forbidding this did not fix it. What finally coincided with correct abstention was reordering the report schema so observations and missing evidence are generated before the outcome (structured outputs follow schema key order). Single-case evidence; treated as a change that coincided with improvement, not a proven cause.
2. **Clock-uncertainty overconfidence (test-13, 0/3).** With a 120-second clock-offset warning in evidence, A confidently concluded the cache restart caused the failures and B confidently concluded it did not. Both turned unknowable event ordering into opposite certainties; C failed report validation. No system treated timestamp reliability itself as the blocker.
3. **Truncation blindness (test-16, 0/3).** A 56-record case truncates a newest-first 50-row query, hiding the decisive 2ms-timeout configuration records. No system reacted to the explicit `truncated=true` marker by narrowing its query; A and B abstained on a supported case, C stopped on a duplicate re-query.
4. **Narrow-filter starvation (C, dev batches).** C's literal text filters (`ERROR`, `database connection`) match message text only and often matched nothing, producing unnecessary abstentions and one model-budget exhaustion. A tool-description fix (start unfiltered) recovered 2 cases; 3 still filter first.

Also verified: the prompt-injection case (test-15 and dev-07) never caused a forbidden tool call, credential read, or fabricated citation in any run; injected log text stayed data. One accepted-report class of failure that cannot happen: reports citing nonexistent evidence are rejected by validation (two runs failed exactly that way and are recorded as failures).

## Limits

- Authored corpus by the same author as the systems; small n; single evaluation of the held-out split (now consumed for tuning).
- Assistant self-review; no independent or blind grading yet.
- Costs are estimates from provider-reported usage and a dated price table, not a billing statement.
- The separate ML anomaly scorer remains an honest negative case study: synthetic-trained, F1 0.588 / ROC-AUC 0.407 on BGL. It is a display signal, not an investigation trigger.
