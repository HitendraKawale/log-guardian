# First live baseline smoke evaluation

Four real OpenAI requests on two authored development cases, run on 2026-09-13. These are recorded model results, not production incidents or a held-out benchmark. Each system ran once per case. No prompt, model, or evidence changed between requests.

## Results

| Case | System | Expected outcome | Model outcome | Core diagnosis review | Input/output tokens | Seconds | Estimated USD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dev-01 | A | supported | supported | Matches the deadline mechanism | 918 / 276 | 4.339 | 0.00080880 |
| dev-01 | B | supported | supported | Matches the deadline mechanism; health overclaim below | 1569 / 246 | 2.920 | 0.00102120 |
| dev-06 | A | inconclusive | supported | Unsupported causal link | 798 / 240 | 2.928 | 0.00070320 |
| dev-06 | B | inconclusive | supported | Unsupported causal link | 1785 / 264 | 3.441 | 0.00113640 |

All four requests completed, passed report-schema/citation-membership validation, and stayed within configured resource limits. That does not mean four correct reports. Two core diagnoses match the development rubric; both required abstentions failed. Correct abstentions: **0 of 2**. No inconclusive model report was produced.

Total estimated cost: **$0.00366960**, calculated from returned usage and the dated price table, not an invoice reconciliation. All four authorized requests are consumed despite the remaining dollar allowance. There were no retries or unknown-usage failures.

## What the reports actually support

On dev-01, both reports identify inventory's 5340ms handling time exceeding checkout's 5000ms deadline. Neither establishes why inventory was slow. Their suggested database/network checks are proposals, not evidence that those components failed.

A's second observation cites `dev-01:05` for both the 5340ms duration and the 5000ms deadline, although that record only contains the duration. The deadline appears elsewhere in the supplied evidence. Citation existence alone misses this incomplete attribution.

B's health-probe observation says the service was "generally healthy." `dev-01:06` only establishes that one probe succeeded. That generalization is unsupported, even though the report's core timeout explanation matches the rubric. Do not advertise the whole report as fully grounded.

## Failure: missing telemetry became an invented cause

Both dev-06 reports claim that the collector's failure to provide search log data caused gateway requests to time out. The cited collector record only reports unavailable log export. No record establishes that gateway requests depend on the collector, or that missing log export delayed search responses.

The intended conclusion is inconclusive: gateway timeouts are observed, but search-side logs or traces and transport/handler timing evidence are missing. The reports instead propose checks that assume the invented collector-to-request dependency. These are semantic failures with valid citation IDs, not provider outages or schema failures.

The original reports remain unchanged in `dev-06-A.json` and `dev-06-B.json`. Their `status="completed"` records successful runner execution, not evaluation success. Neither can satisfy the plan's inconclusive-example requirement.

## Failure: fixed retrieval selected weak context

For dev-06, B retrieved `benign-errors`, `connection-pools`, and `credentials-configuration`, with `truncated=true`. It did not supply `insufficient-evidence` or `timeouts`. The current lexical ranker counts shared words without stop-word filtering, then breaks ties by section ID. This result exposes a retrieval weakness; it does not prove that better retrieval alone would fix abstention.

For dev-01, B retrieved only `insufficient-evidence`. More retrieval therefore did not consistently mean more relevant procedural guidance. This four-request sample cannot establish whether A or B is better generally.

## Provenance and verification

- Model requested and returned: `gpt-4.1-mini-2025-04-14`; SDK: `2.11.0`; temperature: 0.
- Clean code revision: `e4edf8bdc33e5df6f666518ee146f74a46058e12`.
- Dataset: authored development corpus `1.0.0`; cases selected offline from the existing rubric. Labels were not passed to the runtime runner.
- Each JSON contains prompt/schema, case, corpus, and implementation hashes, exact sanitized evidence snapshots, returned usage, timings, and limits. `summary.json` includes byte-level artifact hashes and the offline outcome comparison.
- The coding assistant reviewed claims against evidence and the existing rubric. This was not independent or blind review; no supported-claim precision score is asserted.
- Before calls: `make test` passed 177 tests; `make lint` printed `All checks passed!` and `66 files already formatted`.
- After calls: all four report schemas and citation memberships were revalidated, each result was checked against the byte bound, and request/output/time/cost limits were checked. Original JSON bytes were preserved.

## Next decision

Step 5's live development evaluation is complete. Step 6 remains open because both baselines failed to produce an inconclusive report. Keep PR #16 draft. Diagnose and test any prompt/retrieval change offline, retain this comparison as the original version, and obtain a new request allowance before another paid evaluation. Do not proceed to the adaptive phase by relabeling these failures.
